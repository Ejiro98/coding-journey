"""Clips on Higgsfield: estimate the whole batch, check the budget, then generate.

CHAIN MODE (video.chain, default on): every clip starts from the exact last frame
of the clip before it, so the video flows as one continuous build with no jumps.
A clip marked "cut": true starts fresh from its own keyframe (a deliberate scene
change, e.g. from the shaft to a hallway). The "to" keyframe is where the clip must
END, which anchors each build step so it can't drift.

If an earlier clip is remade, every chained clip after it is out of date and is
remade too (the estimate shows this before anything is paid for). Idempotency keys
are stored in state.json, so re-running after a crash never pays twice.
"""

import hashlib
import subprocess

from . import higgsfield as hf, http, ledger, timing


def chain_on(data):
    return data.get("video", {}).get("chain", True)


def clip_prompt(data, clip):
    parts = []
    if clip.get("cue"):
        parts.append("The action starts immediately, in the first half second.")
    parts.append(clip["motion"].strip())
    rules = data.get("rules", [])
    if rules:
        parts.append("Always true: " + " ".join(r.strip() for r in rules))
    return " ".join(parts)


def last_frame(src, dst):
    """Write the final frame of a clip to dst (PNG)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(["ffmpeg", "-y", "-v", "error", "-sseof", "-0.5", "-i", str(src),
                           "-update", "1", "-q:v", "2", str(dst)], capture_output=True, text=True)
    if proc.returncode != 0 or not dst.exists():
        raise RuntimeError(f"Couldn't read the last frame of {src.name}: {proc.stderr[-300:]}")
    return dst


def _size(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    try:
        w, h = (int(x) for x in out.strip().split(",")[:2])
        return w, h
    except ValueError:
        return None


def match_size(start, end):
    """Some models (Seedance) refuse a first and last frame of different sizes. When a chained
    clip starts from a video frame (e.g. 480x854) and ends on a keyframe (e.g. 768x1376), scale
    the start image to the keyframe's exact size. Returns the image to upload."""
    a, b = _size(start), _size(end)
    if not a or not b or a == b:
        return start
    out = start.with_name(f"{start.stem}_{b[0]}x{b[1]}.png")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(start), "-vf",
                    f"scale={b[0]}:{b[1]}:force_original_aspect_ratio=increase,crop={b[0]}:{b[1]}",
                    str(out)], check=True)
    return out


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def _start_image(project, data, clips, idx):
    """The image clip idx must start from right now, and where it came from."""
    clip = clips[idx]
    if chain_on(data) and idx > 0 and not clip.get("cut"):
        prev = clips[idx - 1]["id"]
        prev_file = project.clip_file(prev)
        if prev_file:
            return last_frame(prev_file, project.path("build", "chain", f"{prev}_last.png")), f"end of {prev}"
        return None, f"end of {prev} (not made yet)"
    return project.frame_file(clip["from"]), f"keyframe {clip['from']}"


def plan(project, data, model=None, only=None, words=None, next_n=None):
    """Work out which clips must be (re)made, in order. Returns list of dicts."""
    model = model or data.get("video", {}).get("model", "wan3")
    if model not in hf.VIDEO_MODELS:
        raise ValueError(f"Unknown model {model}. Choose from {', '.join(hf.VIDEO_MODELS)}")
    if words is None:
        words, _ = timing.load_words(project, data, project.setting(data, "words_per_minute"))
    segs, _ = timing.segments(data, words, project.setting(data, "end_hold_seconds"))
    secs = {s["clip"]: s["seconds"] for s in segs}
    wanted = {c.strip() for c in only.split(",")} if only else None
    state = project.load_state()
    clips = data["clips"]
    todo, dirty, notes = [], False, []
    for idx, clip in enumerate(clips):
        cid = clip["id"]
        chained = chain_on(data) and idx > 0 and not clip.get("cut")
        if not chained:
            dirty = False
        selected = wanted is None or cid in wanted
        exists = project.clip_file(cid) is not None
        stale = False
        if exists and chained:
            if dirty:
                stale = True
            else:
                img, _ = _start_image(project, data, clips, idx)
                rec = state["clips"].get(cid, {})
                stale = img is not None and rec.get("start_sha") not in (None, _sha(img))
        need = (not exists) or stale
        if need and not selected:
            if exists and stale:
                notes.append(f"{cid} is out of date (an earlier clip changed) but not selected")
            dirty = dirty or not exists
            continue
        if need:
            if next_n and len(todo) >= int(next_n):
                break
            for fid in [clip["from"]] + ([clip["to"]] if clip.get("to") else []):
                if not project.frame_file(fid):
                    raise ValueError(f"Clip {cid} needs keyframe {fid}; make it first.")
            clip_model = clip.get("model") or model   # per-clip override (e.g. Seedance for a hard shot)
            if clip_model not in hf.VIDEO_MODELS:
                raise ValueError(f"Clip {cid}: unknown model {clip_model}")
            todo.append({"clip": clip, "idx": idx, "seconds": secs[cid], "model": clip_model,
                         "why": "out of date" if stale else "new"})
            dirty = True
    return todo, notes


def build_requests(project, data, model=None, only=None, words=None):
    """Compatibility helper: [(clip, seconds, model)] still to make."""
    todo, _ = plan(project, data, model, only, words)
    return [(t["clip"], t["seconds"], t["model"]) for t in todo]


def planning_total(reqs, resolution="720p"):
    total, unknown = 0.0, []
    for clip, secs, model in reqs:
        c = hf.planning_cost(model, secs, resolution)
        if c is None:
            unknown.append(clip["id"])
        else:
            total += c
    return round(total, 2), unknown


def _upload_cached(client, project, state, path):
    key = f"{path.name}:{_sha(path)}"
    if key not in state["uploads"]:
        state["uploads"][key] = client.upload(path)
        project.save_state(state)
    return state["uploads"][key]


def _body(project, data, client, state, item, start_img):
    clip = item["clip"]
    res = data.get("video", {}).get("resolution", "720p")
    end_img = project.frame_file(clip["to"]) if clip.get("to") else None
    if end_img is None and clip.get("hold"):
        # A hold clip with no end still let the model invent the next story beat (landfill C01 drew
        # the leak 2.5 s in). Ending on its own still pins it: only small motion can happen.
        end_img = project.frame_file(clip["from"])
    if end_img is not None:
        start_img = match_size(start_img, end_img)
    start = _upload_cached(client, project, state, start_img)
    end = _upload_cached(client, project, state, end_img) if end_img is not None else None
    res = clip.get("resolution") or res
    return hf.clip_body(item["model"], start, end, clip_prompt(data, clip), item["seconds"], res)


def estimate(project, data, client, model=None, only=None, next_n=None):
    todo, notes = plan(project, data, model, only, next_n=next_n)
    state = project.load_state()
    rows, total = [], 0.0
    for item in todo:
        # The cost depends on model and length, not on the picture, so a chained clip
        # whose start frame doesn't exist yet is estimated with its keyframe.
        img, _ = _start_image(project, data, data["clips"], item["idx"])
        body = _body(project, data, client, state, item, img or project.frame_file(item["clip"]["from"]))
        usd = client.estimate(hf.VIDEO_MODELS[item["model"]]["endpoint"], body)
        rows.append({**item, "clip_id": item["clip"]["id"], "usd": usd, "duration": body["duration"]})
        total += usd
    return rows, round(total, 4), notes


def run(project, data, client, approve_usd, model=None, only=None, log=print, next_n=None):
    rows, total, notes = estimate(project, data, client, model, only, next_n)
    for n in notes:
        log(f"note: {n}")
    if not rows:
        log("Nothing to make: every selected clip exists and is up to date.")
        return []
    for r in rows:
        ledger.append(project, "estimate", "higgsfield", r["clip_id"], r["usd"])
    ledger.guard(project, data, total, approve_usd)
    state = project.load_state()
    made = []
    for r in rows:
        cid = r["clip_id"]
        img, source = _start_image(project, data, data["clips"], r["idx"])
        if img is None:
            log(f"{cid}: stopped, it must start from the {source}. Make that clip first.")
            break
        body = _body(project, data, client, state, r, img)
        endpoint = hf.VIDEO_MODELS[r["model"]]["endpoint"]
        rec = state["clips"].get(cid, {})
        if rec.get("body") != body:
            rec = {"idempotency_key": hf.new_idempotency_key(), "body": body, "model": r["model"]}
        if not rec.get("status_url"):
            sub = client.submit(endpoint, body, rec["idempotency_key"])
            rec.update(request_id=sub.get("request_id"), status_url=sub.get("status_url"), status="submitted")
            state["clips"][cid] = rec
            project.save_state(state)
            log(f"{cid}: submitted ({r['duration']}s from {source}, est ${r['usd']:.3f})")
        res = client.wait(rec["status_url"])
        rec["status"] = res["status"]
        if res["status"] != "completed":
            rec.pop("status_url", None)  # allow a fresh attempt next run
            # A failed request is never charged, and reusing its idempotency key would make
            # Higgsfield replay the same failure (e.g. "credit balance too low" after a top-up).
            rec["idempotency_key"] = hf.new_idempotency_key()
            state["clips"][cid] = rec
            project.save_state(state)
            log(f"{cid}: {res['status']} (not charged) {res.get('error', '')}")
            if chain_on(data):
                log("Stopping: the next chained clip needs this one. Soften its motion text and re-run.")
                break
            continue
        dest = project.path("clips", f"{cid}.mp4")
        http.download(hf.output_url(res), dest)
        rec.update(file=dest.name, start_sha=_sha(img), start_source=source)
        state["clips"][cid] = rec
        project.save_state(state)
        ledger.append(project, "spend", "higgsfield", cid, r["usd"], request_id=rec.get("request_id"))
        log(f"{cid}: done -> clips/{dest.name}")
        made.append(cid)
    return made


def checklist(data, clip):
    """Yes/no questions a SEPARATE reviewer answers from the clip's frames (see review_sheet).
    Any 'no' (or 'yes' on a MUST-BE-NO question) means remake that clip before making the next."""
    lines = {str(l["id"]): l["text"] for l in data.get("lines", [])}
    idx = [c["id"] for c in data["clips"]].index(clip["id"])
    qs = [f"Does the clip show exactly this, as ONE smooth change: \"{clip['motion'].strip()}\"?"]
    if clip.get("cue"):
        qs.append(f"Does the action start right away (first half second), since it starts on the word "
                  f"\"{clip['cue']}\"?")
    for lid in clip.get("lines", []):
        if str(lid) in lines:
            qs.append(f"Say it, see it: while \"{lines[str(lid)]}\" is spoken, is what it names on screen?")
    if chain_on(data) and idx > 0 and not clip.get("cut"):
        qs.append(f"Does the first frame continue smoothly from the last frame of {data['clips'][idx - 1]['id']} "
                  "(no jump in camera, colour or objects)?")
    if clip.get("to"):
        qs.append(f"Does the last frame match the end still {clip['to']} (same objects, places and levels)?")
    if clip.get("move"):
        qs.append(f"Does the camera {clip['move']} smoothly, by no more than about 2x, with no cut?")
    else:
        qs.append("Does the camera stay completely still the whole time?")
    qs.append("MUST BE NO: does anything appear from nowhere, vanish, teleport, melt, morph or change kind "
              "(e.g. white gulls turning into dark birds, a machine fading in, pipes changing number)?")
    qs.append("MUST BE NO: is there a cut, flash, freeze or sudden jump anywhere?")
    if data.get("rules"):
        qs.append("MUST BE NO: does anything break these rules: " + " ".join(data["rules"]))
    qs.append("MUST BE NO: is there any text, letters, logo or watermark?")
    return qs


def review_sheet(project, clip_id, fps=4, cols=6):
    """Frames from the clip at `fps`, tiled into one image for the reviewer, plus the previous
    clip's last frame. Returns (sheet path, previous-last-frame path or None)."""
    import math
    src = project.clip_file(clip_id)
    if not src:
        raise ValueError(f"{clip_id} has no clip yet.")
    n = max(1, math.ceil(_duration(src) * fps))
    rows = math.ceil(n / cols)
    out = project.path("build", "review", f"{clip_id}_sheet.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf",
                    f"fps={fps},scale=320:-2,tile={cols}x{rows}", "-frames:v", "1", str(out)], check=True)
    return out


def _duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def trim(project, data, clip_id, end_s=None, start_s=0.0):
    """FREE: keep the part of a clip from `start_s` to `end_s` (cut a slow start, or an end that went wrong).
    Only worth it if what's left still fills most of the beat, or the assembly slows it down or
    freezes it. The next chained clip becomes out of date (it must start from the new last frame)."""
    src = project.clip_file(clip_id)
    if not src:
        raise ValueError(f"{clip_id} has no clip yet.")
    words, _ = timing.load_words(project, data, project.setting(data, "words_per_minute"))
    segs, _ = timing.segments(data, words, project.setting(data, "end_hold_seconds"))
    beat = next(s["seconds"] for s in segs if s["clip"] == clip_id)
    keep = src.with_name(f"{clip_id}.untrimmed{src.suffix}")
    if not keep.exists():
        src.replace(keep)
    span = ["-ss", f"{start_s:.3f}"] + (["-t", f"{end_s - start_s:.3f}"] if end_s else [])
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(keep), *span, "-an",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    return src, beat


def pair_sheet(project, data, clip_id, w=540, h=960):
    """FREE check BEFORE paying for a clip: its start picture, its end picture, and a boosted
    difference of the two side by side. Bright areas in the difference are everything the model
    must change. If anything is bright that the motion doesn't describe (a redrawn wall, a moved
    heap, a vanished truck), fix the stills first: the model fills such gaps with invented action
    (landfill C02: four failed clips from a redrawn pit wall)."""
    clips = data["clips"]
    idx = [c["id"] for c in clips].index(clip_id)
    clip = clips[idx]
    start, source = _start_image(project, data, clips, idx)
    if start is None:   # previous clip not made yet: its end still is the best stand-in
        prev = clips[idx - 1]
        start = project.frame_file(prev.get("to") or prev["from"])
        source = f"end still of {prev['id']} (clip not made yet)"
    end = project.frame_file(clip["to"]) if clip.get("to") else (
        project.frame_file(clip["from"]) if clip.get("hold") else None)
    if not start or not end:
        raise ValueError(f"{clip_id}: start or end picture missing.")
    out = project.path("build", "review", f"{clip_id}_pair.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    fit = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},format=rgb24"
    graph = (f"[0:v]{fit},split[a][a2];[1:v]{fit},split[b][b2];"
             f"[a2][b2]blend=all_mode=difference,eq=contrast=4:brightness=0.1[d];[a][b][d]hstack=inputs=3")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(start), "-i", str(end), "-filter_complex", graph,
                    "-frames:v", "1", str(out)], check=True)
    return out, source
