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
            todo.append({"clip": clip, "idx": idx, "seconds": secs[cid], "model": model,
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
    if end_img is not None:
        start_img = match_size(start_img, end_img)
    start = _upload_cached(client, project, state, start_img)
    end = _upload_cached(client, project, state, end_img) if end_img is not None else None
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
