"""Keyframes.

Default route is Google Flow (free Nano Banana, daily limit) driven by Claude
through the Flow MCP on the Mac: `frames prompts` prints each frame's prompt and
reference files, and `frames import` brings the downloaded image into the project.
Paid fallbacks (Gemini API, Higgsfield image edit) go through the budget guard.
"""

import shutil

from . import ledger, quota
from .project import frame_map

CONSISTENCY = (
    "Use the reference image(s) as the previous frame of the same animation. Keep everything "
    "identical: same building, same camera position and angle, same lighting, same materials, "
    "same box. Change ONLY the following: "
)


def build_state(data, frame):
    """Which parts exist in this frame, from the script line whose state it shows."""
    parts = data.get("parts", {})
    order = [str(l["id"]) for l in data["lines"]]
    state = frame.get("state")
    if state is None or not parts:
        return [], []
    upto = order.index(str(state))
    built, missing = [], []
    for name, spec in parts.items():
        looks = spec.get("looks") or name
        (built if order.index(str(spec["built_in"])) <= upto else missing).append(looks)
    return built, missing


def prompt_for(data, frame):
    style = data.get("style", "").strip()
    body = frame["shows"].strip()
    built, missing = build_state(data, frame)
    extra = ""
    if frame.get("wide") and built:
        extra += " Already built and clearly visible: " + "; ".join(built) + "."
    if missing:
        extra += (" NOT BUILT YET, do not draw any of these anywhere in the image: "
                  + "; ".join(missing) + ".")
    if not frame.get("refs"):
        return f"{style} {body}{extra}".strip()
    first_ref = frame_map(data).get(frame["refs"][0], {})
    if frame.get("view") and first_ref.get("view") and frame["view"] != first_ref["view"]:
        moved = (f"Use the reference image(s) as the same scene a moment later. Keep every object, material, "
                 f"colour and the lighting identical, but the camera has moved: "
                 f"{frame.get('camera', 'closer to the subject')}. Then: ")
        return f"{style} {moved}{body}{extra}".strip()
    return f"{style} {CONSISTENCY}{body}{extra}".strip()


def plan(project, data):
    """One entry per frame: prompt, reference files to attach, and whether it's ready to make."""
    out = []
    for f in data.get("frames", []):
        refs = []
        missing = []
        for r in f.get("refs", []):
            p = project.frame_file(r)
            (refs if p else missing).append(str(p) if p else r)
        out.append({
            "id": f["id"],
            "done": project.frame_file(f["id"]) is not None,
            "ready": not missing,
            "waiting_for": missing,
            "refs": refs,
            "prompt": prompt_for(data, f),
        })
    return out


def import_frame(project, frame_id, src, source="flow"):
    data = project.load()
    if frame_id not in frame_map(data):
        raise ValueError(f"Unknown frame {frame_id}")
    ext = src.suffix.lower() if src.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp") else ".png"
    old = project.frame_file(frame_id)
    if old:
        old.rename(old.with_name(f"{frame_id}.prev{old.suffix}"))
    dest = project.path("frames", f"{frame_id}{ext}")
    shutil.copyfile(src, dest)
    state = project.load_state()
    state["frames"][frame_id] = {"file": dest.name, "source": source}
    project.save_state(state)
    if source == "flow":
        quota.add(1)
    return dest


def make_with_gemini(project, data, frame_id, approve_usd, gemini_mod=None):
    from . import config
    from . import gemini as g
    gemini_mod = gemini_mod or g
    frame = frame_map(data)[frame_id]
    price = float(data.get("settings", {}).get("gemini_usd_per_image", config.DEFAULTS["gemini_usd_per_image"]))
    ledger.guard(project, data, price, approve_usd)
    refs = [project.frame_file(r) for r in frame.get("refs", [])]
    if any(r is None for r in refs):
        raise ValueError(f"Make {frame['refs']} first; they are references for {frame_id}.")
    img = gemini_mod.generate_image(prompt_for(data, frame), refs)
    dest = project.path("frames", f"{frame_id}.png")
    dest.write_bytes(img)
    ledger.append(project, "spend", "gemini", frame_id, price, note="planning price; check Google billing")
    state = project.load_state()
    state["frames"][frame_id] = {"file": dest.name, "source": "gemini"}
    project.save_state(state)
    return dest


def make_with_kie(project, data, frame_id, approve_usd, kie_mod=None, sleep=None):
    """Cheapest paid fallback: Nano Banana Pro on kie.ai (~$0.09 at 2K). Logs the real charge."""
    from . import config
    from . import kie as k
    kie_mod = kie_mod or k
    frame = frame_map(data)[frame_id]
    price = float(data.get("settings", {}).get("kie_usd_per_image", config.DEFAULTS["kie_usd_per_image"]))
    ledger.guard(project, data, price, approve_usd)
    refs = [project.frame_file(r) for r in frame.get("refs", [])]
    if any(r is None for r in refs):
        raise ValueError(f"Make {frame['refs']} first; they are references for {frame_id}.")
    kwargs = {"sleep": sleep} if sleep else {}
    img, usd, task = kie_mod.nano_banana_pro(prompt_for(data, frame), refs, **kwargs)
    dest = project.path("frames", f"{frame_id}.png")
    old = project.frame_file(frame_id)
    if old and old != dest:
        old.rename(old.with_name(f"{frame_id}.prev{old.suffix}"))
    dest.write_bytes(img)
    ledger.append(project, "spend", "kie", frame_id, usd or price, task_id=task)
    state = project.load_state()
    state["frames"][frame_id] = {"file": dest.name, "source": "kie:nano-banana-pro"}
    project.save_state(state)
    return dest


def make_with_higgsfield(project, data, frame_id, approve_usd, client=None, model="qwen-edit"):
    from . import higgsfield as hf, http
    client = client or hf.Client()
    frame = frame_map(data)[frame_id]
    refs = [project.frame_file(r) for r in frame.get("refs", [])]
    if not refs or any(r is None for r in refs):
        raise ValueError("Higgsfield image edit needs the reference frames to exist (it can't make F01).")
    urls = [client.upload(r) for r in refs]
    body = hf.image_body(model, prompt_for(data, frame), urls)
    endpoint = hf.IMAGE_MODELS[model]["endpoint"]
    est = client.estimate(endpoint, body)
    ledger.append(project, "estimate", "higgsfield", frame_id, est)
    ledger.guard(project, data, est, approve_usd)
    sub = client.submit(endpoint, body, hf.new_idempotency_key())
    res = client.wait(sub["status_url"])
    if res["status"] != "completed":
        raise RuntimeError(f"{frame_id} ended {res['status']} (not charged): {res.get('error', '')}")
    dest = project.path("frames", f"{frame_id}.png")
    http.download(hf.output_url(res), dest)
    ledger.append(project, "spend", "higgsfield", frame_id, est, request_id=sub.get("request_id"))
    state = project.load_state()
    state["frames"][frame_id] = {"file": dest.name, "source": f"higgsfield:{model}"}
    project.save_state(state)
    return dest
