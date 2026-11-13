"""Model comparison: make the same clips on several Higgsfield models and put the
results side by side, so the model is chosen on evidence before a full video is paid for.

Each model gets its own chain (its second clip starts from ITS first clip's last frame),
exactly as a real video would. Outputs: projects/<slug>/compare/<model>/<clip>.mp4 and
compare/side_by_side.mp4 (labelled columns). Every spend goes through the budget guard.
"""

import subprocess

from . import clips as clp, higgsfield as hf, http, ledger, timing


def _clip_list(data, ids):
    wanted = [c.strip() for c in ids.split(",")] if ids else [c["id"] for c in data["clips"][:2]]
    by_id = {c["id"]: c for c in data["clips"]}
    missing = [i for i in wanted if i not in by_id]
    if missing:
        raise ValueError(f"Unknown clips: {missing}")
    return [by_id[i] for i in wanted]


def plan(project, data, models, ids=None):
    words, _ = timing.load_words(project, data, project.setting(data, "words_per_minute"))
    segs, _ = timing.segments(data, words, project.setting(data, "end_hold_seconds"))
    secs = {s["clip"]: s["seconds"] for s in segs}
    chosen = _clip_list(data, ids)
    for c in chosen:
        for fid in [c["from"]] + ([c["to"]] if c.get("to") else []):
            if not project.frame_file(fid):
                raise ValueError(f"Clip {c['id']} needs keyframe {fid}; make it first.")
    for m in models:
        if m not in hf.VIDEO_MODELS:
            raise ValueError(f"Unknown model {m}. Choose from {', '.join(hf.VIDEO_MODELS)}")
    return chosen, secs


def estimate(project, data, client, models, ids=None):
    chosen, secs = plan(project, data, models, ids)
    state = project.load_state()
    rows, total = [], 0.0
    for m in models:
        for c in chosen:
            item = {"clip": c, "model": m, "seconds": secs[c["id"]]}
            body = clp._body(project, data, client, state, item, project.frame_file(c["from"]))
            usd = client.estimate(hf.VIDEO_MODELS[m]["endpoint"], body)
            rows.append({"clip": c["id"], "model": m, "duration": body["duration"], "usd": usd})
            total += usd
    return rows, round(total, 4)


def run(project, data, client, models, approve_usd, ids=None, log=print):
    rows, total = estimate(project, data, client, models, ids)
    ledger.guard(project, data, total, approve_usd)
    chosen, secs = plan(project, data, models, ids)
    state = project.load_state()
    results = {}
    for m in models:
        prev_out = None
        for c in chosen:
            out = project.path("compare", m, f"{c['id']}.mp4")
            if out.exists():
                prev_out = out
                continue
            if prev_out is not None and not c.get("cut"):
                start = clp.last_frame(prev_out, project.path("compare", m, f"{c['id']}_start.png"))
            else:
                start = project.frame_file(c["from"])
            item = {"clip": c, "model": m, "seconds": secs[c["id"]]}
            body = clp._body(project, data, client, state, item, start)
            usd = next(r["usd"] for r in rows if r["clip"] == c["id"] and r["model"] == m)
            sub = client.submit(hf.VIDEO_MODELS[m]["endpoint"], body, hf.new_idempotency_key())
            res = client.wait(sub["status_url"])
            if res["status"] != "completed":
                log(f"{m} {c['id']}: {res['status']} (not charged)")
                break
            http.download(hf.output_url(res), out)
            ledger.append(project, "spend", "higgsfield", f"{c['id']}@{m}", usd, request_id=sub.get("request_id"))
            log(f"{m} {c['id']}: done (${usd:.3f})")
            prev_out = out
        results[m] = [project.dir / "compare" / m / f"{c['id']}.mp4" for c in chosen]
    return side_by_side(project, results)


def side_by_side(project, results, w=360, h=640):
    """One labelled column per model, clips played in order."""
    cols = []
    for m, files in results.items():
        files = [f for f in files if f.exists()]
        if not files:
            continue
        col = project.path("compare", f"col_{m}.mp4")
        inputs = sum((["-i", str(f)] for f in files), [])
        chain = "".join(f"[{i}:v]scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps=30,"
                        f"setsar=1[v{i}];" for i in range(len(files)))
        chain += "".join(f"[v{i}]" for i in range(len(files))) + f"concat=n={len(files)}:v=1:a=0[c]"
        subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", chain, "-map", "[c]",
                        "-pix_fmt", "yuv420p", str(col)], check=True)
        cols.append((m, col))
    if not cols:
        return None
    out = project.path("compare", "side_by_side.mp4")
    inputs = sum((["-i", str(c)] for _, c in cols), [])
    if len(cols) == 1:
        subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-c", "copy", str(out)], check=True)
        return out
    labels = "".join(f"[{i}:v]tpad=stop_mode=clone:stop_duration=30[p{i}];" for i in range(len(cols)))
    stack = "".join(f"[p{i}]" for i in range(len(cols))) + f"hstack=inputs={len(cols)}:shortest=0[s]"
    longest = max(_dur(c) for _, c in cols)
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", labels + stack, "-map", "[s]",
                    "-t", f"{longest:.2f}", "-pix_fmt", "yuv420p", str(out)], check=True)
    (project.dir / "compare" / "columns.txt").write_text(
        "Left to right: " + ", ".join(m for m, _ in cols) + "\n")
    return out


def _dur(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                          str(path)], capture_output=True, text=True).stdout.strip()
    return float(out or 0)
