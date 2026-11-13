"""Higgsfield API client (pay-as-you-go balance, no subscription).

Docs checked Nov 2026: auth `Authorization: Key ID:SECRET`, uploads via
/files/generate-upload-url, cost via /estimate/{endpoint}, submit returns
status_url, poll until completed/failed/nsfw/canceled, output video.url or
images[0].url. Failed and NSFW requests are not charged. Files are deleted
after 7 days, so we download immediately.
"""

import math
import re
import mimetypes
import random
import time
import uuid

from . import config, http

BASE = "https://api.higgsfield.ai"
TERMINAL = {"completed", "failed", "nsfw", "canceled"}

# Video models that take a START frame and an END frame.
# price_per_sec (USD per output second, by resolution) is only a planning hint;
# the /estimate endpoint is authoritative. Kling o3 'std' mode renders 720p.
VIDEO_MODELS = {
    "wan3": {
        "endpoint": "alibaba/wan-3.0/image-to-video",
        "start": "image_url", "end": "end_image_url",
        "min": 2, "max": 30,
        "extra": {"aspect_ratio": "9:16", "generate_audio": False},
        "resolution_field": "resolution",
        "price_per_sec": {"480p": 0.0375, "720p": 0.075, "1080p": 0.15},
    },
    "seedance2": {
        "endpoint": "bytedance/seedance-2.0/image-to-video",
        "start": "image_url", "end": "end_image_url",
        "min": 4, "max": 15,
        "extra": {"generate_audio": False},
        "resolution_field": "resolution",
        "price_per_sec": {"480p": 0.0804, "720p": 0.1735, "1080p": 0.4293},
    },
    "seedance25": {
        "endpoint": "bytedance/seedance-2.5/image-to-video",
        "start": "image_url", "end": "end_image_url",
        "min": 4, "max": 30,
        "extra": {"generate_audio": False},
        "resolution_field": "resolution",
        "price_per_sec": {"480p": 0.1177, "720p": 0.2647, "1080p": 0.6518},
    },
    "kling-o3": {
        "endpoint": "kling-video/o3/first-last-frame",
        "start": "first_frame_url", "end": "last_frame_url",
        "min": 3, "max": 15,
        "extra": {"aspect_ratio": "9:16", "sound": "off", "mode": "std", "multi_shots": False},
        "resolution_field": None,
        "price_per_sec": {"720p": 0.0683, "1080p": 0.086},
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


def credentials():
    """Accept either HF_KEY='id:secret' (one combined key, as Higgsfield's SDK uses)
    or the pair HF_API_KEY_ID + HF_API_KEY_SECRET."""
    if config.has_key("HF_KEY"):
        combined = config.get_key("HF_KEY")
        if ":" not in combined:
            raise config.MissingKey(
                "HF_KEY should look like 'keyid:secret' (two parts joined by a colon). "
                "Yours has no colon, so the secret part is missing. Create a new API key in the "
                "Higgsfield console and copy the whole value."
            )
        key_id, secret = combined.split(":", 1)
        return key_id.strip(), secret.strip()
    return config.get_key("HF_API_KEY_ID"), config.get_key("HF_API_KEY_SECRET")


def has_credentials():
    try:
        credentials()
        return True
    except config.MissingKey:
        return False


class Client:
    def __init__(self, key_id=None, secret=None, base=BASE, sleep=time.sleep):
        if not (key_id and secret):
            key_id, secret = credentials()
        self.key_id = key_id
        self.secret = secret
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
        return price_from_estimate(res, body)

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


def planning_cost(model_name, seconds, resolution="720p"):
    rate = VIDEO_MODELS[model_name]["price_per_sec"].get(resolution)
    if rate is None:
        return None
    return round(clip_duration(model_name, seconds) * rate, 4)


class EstimateUnreadable(RuntimeError):
    pass


def price_from_estimate(res, body):
    """Turn an /estimate reply into USD.

    Higgsfield answers either {"usd": ...} or, as of Nov 2026, a text price list:
    {"type": "description", "pricing_description": "... per video second: 480p: $0.0375;
    720p: $0.0750; ... Total price = selected rate x output duration in seconds."}
    For the text form we take the rate for the request's resolution (720p when the
    model has no resolution field) times body["duration"]. Anything else is refused
    rather than guessed, so the spend guard never runs on a made-up number.
    """
    if "usd" in res:
        return float(res["usd"])
    text = res.get("pricing_description") or ""
    rates = {k.lower(): float(v) for k, v in re.findall(r"(\d+[pPkK]):\s*\$(\d+(?:\.\d+)?)", text)}
    if re.search(r"per (video )?second", text) and rates and "duration" in body:
        resolution = str(body.get("resolution") or "720p").lower()
        if resolution in rates:
            return round(rates[resolution] * float(body["duration"]), 4)
    raise EstimateUnreadable(
        "Could not read a price from Higgsfield's estimate, so nothing was generated (no guessing "
        f"with your money). Send this text to Claude so the reader can be taught this format: {res}")
