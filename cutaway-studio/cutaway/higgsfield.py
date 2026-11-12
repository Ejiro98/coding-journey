"""Higgsfield API client (pay-as-you-go balance, no subscription).

Docs checked Nov 2026: auth `Authorization: Key ID:SECRET`, uploads via
/files/generate-upload-url, cost via /estimate/{endpoint}, submit returns
status_url, poll until completed/failed/nsfw/canceled, output video.url or
images[0].url. Failed and NSFW requests are not charged. Files are deleted
after 7 days, so we download immediately.
"""

import math
import mimetypes
import random
import time
import uuid

from . import config, http

BASE = "https://api.higgsfield.ai"
TERMINAL = {"completed", "failed", "nsfw", "canceled"}

# Video models that take a START frame and an END frame.
# price_per_sec is only a planning hint; the /estimate endpoint is authoritative.
VIDEO_MODELS = {
    "wan3": {
        "endpoint": "alibaba/wan-3.0/image-to-video",
        "start": "image_url", "end": "end_image_url",
        "min": 2, "max": 30,
        "extra": {"aspect_ratio": "9:16", "generate_audio": False},
        "resolution_field": "resolution",
        "price_per_sec": 0.0375,
    },
    "seedance2": {
        "endpoint": "bytedance/seedance-2.0/image-to-video",
        "start": "image_url", "end": "end_image_url",
        "min": 4, "max": 15,
        "extra": {"generate_audio": False},
        "resolution_field": "resolution",
        "price_per_sec": 0.0804,
    },
    "seedance25": {
        "endpoint": "bytedance/seedance-2.5/image-to-video",
        "start": "image_url", "end": "end_image_url",
        "min": 4, "max": 30,
        "extra": {"generate_audio": False},
        "resolution_field": "resolution",
        "price_per_sec": 0.1177,
    },
    "kling-o3": {
        "endpoint": "kling-video/o3/first-last-frame",
        "start": "first_frame_url", "end": "last_frame_url",
        "min": 3, "max": 15,
        "extra": {"aspect_ratio": "9:16", "sound": "off", "mode": "std", "multi_shots": False},
        "resolution_field": None,
        "price_per_sec": None,
    },
}

IMAGE_MODELS = {
    # Edits a frame using up to 3 reference images (previous frame + anchor).
    "qwen-edit": {
        "endpoint": "alibaba/qwen-image-3/edit",
        "extra": {"resolution": "2k", "aspect_ratio": "9:16", "prompt_extend": False, "enable_thinking": False},
        "refs_field": "image_urls", "max_refs": 3,
    },
}

STYLE_SUFFIX = (
    " Keep the same realistic 3D engineering cutaway style, materials, lighting and camera framing "
    "as the start image. Smooth, physically believable motion. No text, no captions."
)


class Client:
    def __init__(self, key_id=None, secret=None, base=BASE, sleep=time.sleep):
        self.key_id = key_id or config.get_key("HF_API_KEY_ID")
        self.secret = secret or config.get_key("HF_API_KEY_SECRET")
        self.base = base
        self.sleep = sleep

    def _auth(self):
        return {"Authorization": f"Key {self.key_id}:{self.secret}"}

    # ---------- files ----------
    def upload(self, path):
        ctype = mimetypes.guess_type(str(path))[0] or "image/png"
        info = http.request_json(
            "POST", f"{self.base}/files/generate-upload-url",
            headers=self._auth(), json_body={"content_type": ctype},
        )
        # Never send our credentials to the presigned storage URL.
        http.request("PUT", info["upload_url"], headers=info.get("upload_headers", {"Content-Type": ctype}),
                     data=path.read_bytes(), timeout=300)
        return info["public_url"]

    # ---------- generation ----------
    def estimate(self, endpoint, body):
        res = http.request_json("POST", f"{self.base}/estimate/{endpoint}", headers=self._auth(), json_body=body)
        return float(res["usd"])

    def submit(self, endpoint, body, idempotency_key):
        headers = self._auth()
        headers["Idempotency-Key"] = idempotency_key
        return http.request_json("POST", f"{self.base}/{endpoint}", headers=headers, json_body=body)

    def status(self, status_url):
        return http.request_json("GET", status_url, headers=self._auth())

    def wait(self, status_url, timeout=1800):
        delay, waited = 2.0, 0.0
        while True:
            res = self.status(status_url)
            if res.get("status") in TERMINAL:
                return res
            if waited > timeout:
                raise TimeoutError(f"Still {res.get('status')} after {timeout}s: {status_url}")
            pause = delay + random.uniform(0, 0.5)
            self.sleep(pause)
            waited += pause
            delay = min(delay * 1.5, 10.0)


def new_idempotency_key():
    return str(uuid.uuid4())


def clip_duration(model_name, seconds):
    m = VIDEO_MODELS[model_name]
    return int(min(max(math.ceil(seconds), m["min"]), m["max"]))


def clip_body(model_name, start_url, end_url, motion, seconds, resolution="720p"):
    m = VIDEO_MODELS[model_name]
    body = {
        "prompt": (motion.strip() + STYLE_SUFFIX).strip(),
        m["start"]: start_url,
        "duration": clip_duration(model_name, seconds),
    }
    if end_url:
        body[m["end"]] = end_url
    if m.get("resolution_field"):
        body[m["resolution_field"]] = resolution
    body.update(m["extra"])
    return body


def image_body(model_name, prompt, ref_urls):
    m = IMAGE_MODELS[model_name]
    body = {"prompt": prompt, m["refs_field"]: list(ref_urls)[: m["max_refs"]]}
    body.update(m["extra"])
    return body


def output_url(result):
    if result.get("video", {}).get("url"):
        return result["video"]["url"]
    images = result.get("images") or []
    if images and images[0].get("url"):
        return images[0]["url"]
    raise ValueError(f"No output URL in result: {list(result.keys())}")


def planning_cost(model_name, seconds):
    m = VIDEO_MODELS[model_name]
    if m["price_per_sec"] is None:
        return None
    return round(clip_duration(model_name, seconds) * m["price_per_sec"], 4)
