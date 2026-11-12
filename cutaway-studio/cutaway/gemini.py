"""Paid fallback for keyframes: Nano Banana through the Gemini API.

Same models as Google Flow, no daily cap, billed per image. Used only when Flow's
free allowance is used up and the viewer approves the cost.
"""

import base64
import mimetypes

from . import config, http

BASE = "https://generativelanguage.googleapis.com/v1beta"


def generate_image(prompt, ref_paths=(), model=None, aspect_ratio="9:16", size="2K", api_key=None):
    model = model or config.DEFAULTS["gemini_image_model"]
    parts = [{"text": prompt}]
    for p in ref_paths:
        mime = mimetypes.guess_type(str(p))[0] or "image/png"
        parts.append({"inline_data": {"mime_type": mime, "data": base64.b64encode(p.read_bytes()).decode()}})
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {"aspectRatio": aspect_ratio, "imageSize": size},
        },
    }
    res = http.request_json(
        "POST", f"{BASE}/models/{model}:generateContent",
        headers={"x-goog-api-key": api_key or config.get_key("GEMINI_API_KEY")},
        json_body=body, timeout=300,
    )
    for cand in res.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            blob = part.get("inlineData") or part.get("inline_data")
            if blob and blob.get("data"):
                return base64.b64decode(blob["data"])
    reason = res.get("promptFeedback") or [c.get("finishReason") for c in res.get("candidates", [])]
    raise RuntimeError(f"Gemini returned no image ({reason}). Soften the prompt and retry.")
