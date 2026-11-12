"""Clips on Higgsfield: estimate the whole batch, check the budget, then generate.

Each clip is a start frame (+ optional end frame) and a motion prompt, timed to
the narration segment it covers. Idempotency keys are stored in state.json, so
re-running after a crash never pays twice for the same clip.
"""

from . import higgsfield as hf, http, ledger, timing


def _selected(data, only):
    clips = data["clips"]
    if only:
        wanted = {c.strip() for c in only.split(",")}
        clips = [c for c in clips if c["id"] in wanted]
    return clips


def build_requests(project, data, model=None, only=None, words=None):
    """Return [(clip, seconds, model_name)] for clips still to make."""
    model = model or data.get("video", {}).get("model", "wan3")
    if model not in hf.VIDEO_MODELS:
        raise ValueError(f"Unknown model {model}. Choose from {', '.join(hf.VIDEO_MODELS)}")
    if words is None:
        words, _ = timing.load_words(project, data, project.setting(data, "words_per_minute"))
    segs, _ = timing.segments(data, words, project.setting(data, "end_hold_seconds"))
    secs = {s["clip"]: s["seconds"] for s in segs}
    out = []
    for clip in _selected(data, only):
        if project.clip_file(clip["id"]):
            continue
        for fid in [clip["from"]] + ([clip["to"]] if clip.get("to") else []):
            if not project.frame_file(fid):
                raise ValueError(f"Clip {clip['id']} needs frame {fid}; make it first.")
        out.append((clip, secs[clip["id"]], model))
    return out


def planning_total(reqs):
    total, unknown = 0.0, []
    for clip, secs, model in reqs:
        c = hf.planning_cost(model, secs)
        if c is None:
            unknown.append(clip["id"])
        else:
            total += c
    return round(total, 2), unknown


def _upload_cached(client, project, state, frame_id):
    path = project.frame_file(frame_id)
    key = f"{frame_id}:{path.stat().st_mtime_ns}"
    if key not in state["uploads"]:
        state["uploads"][key] = client.upload(path)
        project.save_state(state)
    return state["uploads"][key]


def estimate(project, data, client, model=None, only=None):
    reqs = build_requests(project, data, model, only)
    state = project.load_state()
    rows, total = [], 0.0
    res = data.get("video", {}).get("resolution", "720p")
    for clip, secs, m in reqs:
        start = _upload_cached(client, project, state, clip["from"])
        end = _upload_cached(client, project, state, clip["to"]) if clip.get("to") else None
        body = hf.clip_body(m, start, end, clip["motion"], secs, res)
        usd = client.estimate(hf.VIDEO_MODELS[m]["endpoint"], body)
        rows.append({"clip": clip["id"], "seconds": body["duration"], "usd": usd, "body": body, "model": m})
        total += usd
    return rows, round(total, 4)


def run(project, data, client, approve_usd, model=None, only=None, log=print):
    rows, total = estimate(project, data, client, model, only)
    if not rows:
        log("Nothing to make: every selected clip already exists.")
        return []
    for r in rows:
        ledger.append(project, "estimate", "higgsfield", r["clip"], r["usd"])
    ledger.guard(project, data, total, approve_usd)
    state = project.load_state()
    made = []
    for r in rows:
        cid = r["clip"]
        endpoint = hf.VIDEO_MODELS[r["model"]]["endpoint"]
        rec = state["clips"].get(cid, {})
        if rec.get("body") != r["body"]:
            rec = {"idempotency_key": hf.new_idempotency_key(), "body": r["body"], "model": r["model"]}
        if not rec.get("status_url"):
            sub = client.submit(endpoint, r["body"], rec["idempotency_key"])
            rec.update(request_id=sub.get("request_id"), status_url=sub.get("status_url"), status="submitted")
            state["clips"][cid] = rec
            project.save_state(state)
            log(f"{cid}: submitted ({r['seconds']}s, est ${r['usd']:.3f})")
        res = client.wait(rec["status_url"])
        rec["status"] = res["status"]
        if res["status"] != "completed":
            rec.pop("status_url", None)  # allow a fresh attempt next run
            state["clips"][cid] = rec
            project.save_state(state)
            log(f"{cid}: {res['status']} (not charged) {res.get('error', '')}")
            continue
        dest = project.path("clips", f"{cid}.mp4")
        http.download(hf.output_url(res), dest)
        rec["file"] = dest.name
        state["clips"][cid] = rec
        project.save_state(state)
        ledger.append(project, "spend", "higgsfield", cid, r["usd"], request_id=rec.get("request_id"))
        log(f"{cid}: done -> clips/{dest.name}")
        made.append(cid)
    return made
