"""kie.ai client: cheapest paid route to Nano Banana Pro (from ~$0.09 per image at 1K/2K).

Docs checked Nov 2026 (docs.kie.ai): Bearer auth; POST /api/v1/jobs/createTask with
model "nano-banana-pro" and input {prompt, image_input (<=8 URLs), aspect_ratio,
resolution, output_format}; poll GET /api/v1/jobs/recordInfo?taskId= until state is
success or fail; resultJson holds resultUrls; creditsConsumed is the real charge
(0 for failed tasks). Reference images go up via the base64 upload endpoint.
kie.ai can answer HTTP 200 with an error code in the body (e.g. 402 = not enough
credits), so every response's "code" is checked.
"""

import base64
import json
import mimetypes
import random
import time

from . import config, http

API = "https://api.kie.ai/api/v1"
UPLOAD = "https://kieai.redpandaai.co/api/file-base64-upload"
USD_PER_CREDIT = 0.005          # kie.ai pricing page: 1 credit ≈ $0.005
NBP = "nano-banana-pro"
MAX_REFS = 8


class KieError(RuntimeError):
    pass


def _headers(key=None):
    return {"Authorization": f"Bearer {key or config.get_key('KIE_API_KEY')}"}


def _checked(res, what):
    code = res.get("code")
    if code not in (200, None):
        raise KieError(f"kie.ai {what} failed ({code}): {res.get('msg') or res.get('message')}")
    return res


def credits(key=None):
    res = _checked(http.request_json("GET", f"{API}/chat/credit", headers=_headers(key), retries=1), "credit check")
    return float(res.get("data") or 0)


def upload(path, key=None):
    mime = mimetypes.guess_type(str(path))[0] or "image/png"
    data_url = f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"
    res = _checked(http.request_json("POST", UPLOAD, headers=_headers(key), json_body={
        "base64Data": data_url, "uploadPath": "cutaway-studio", "fileName": path.name,
    }), "upload")
    d = res.get("data") or {}
    url = d.get("downloadUrl") or d.get("fileUrl") or res.get("downloadUrl")
    if not url:
        raise KieError(f"kie.ai upload returned no URL: {list(res)}")
    return url


def create_task(model, inp, key=None):
    res = _checked(http.request_json("POST", f"{API}/jobs/createTask", headers=_headers(key),
                                     json_body={"model": model, "input": inp}), "createTask")
    task = (res.get("data") or {}).get("taskId")
    if not task:
        raise KieError("kie.ai createTask returned no taskId")
    return task


def record(task_id, key=None):
    res = _checked(http.request_json("GET", f"{API}/jobs/recordInfo?taskId={task_id}", headers=_headers(key)),
                   "recordInfo")
    d = res.get("data") or {}
    urls = []
    try:
        r = json.loads(d.get("resultJson") or "{}")
        urls = r.get("resultUrls") or r.get("result_urls") or []
    except ValueError:
        pass
    return {"state": d.get("state"), "urls": urls, "credits": d.get("creditsConsumed"),
            "error": d.get("failMsg"), "code": d.get("failCode")}


def wait(task_id, key=None, timeout=600, sleep=time.sleep):
    delay, waited = 2.0, 0.0
    while True:
        r = record(task_id, key)
        if r["state"] in ("success", "fail"):
            return r
        if waited > timeout:
            raise TimeoutError(f"kie.ai task {task_id} still {r['state']} after {timeout}s")
        pause = delay + random.uniform(0, 0.5)
        sleep(pause)
        waited += pause
        delay = min(delay * 1.5, 10.0)


def nano_banana_pro(prompt, ref_paths=(), resolution="2K", aspect_ratio="9:16", key=None, sleep=time.sleep):
    """Returns (image_bytes, usd_charged)."""
    refs = [upload(p, key) for p in list(ref_paths)[:MAX_REFS]]
    task = create_task(NBP, {"prompt": prompt, "image_input": refs, "aspect_ratio": aspect_ratio,
                             "resolution": resolution, "output_format": "png"}, key)
    r = wait(task, key, sleep=sleep)
    if r["state"] != "success" or not r["urls"]:
        raise KieError(f"kie.ai image failed (not charged): {r['error'] or r['code'] or 'no result'}")
    _, _, payload = http.request("GET", r["urls"][0], timeout=300)
    usd = round(float(r["credits"] or 0) * USD_PER_CREDIT, 4)
    return payload, usd, task
