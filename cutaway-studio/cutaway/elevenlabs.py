"""ElevenLabs voiceover with exact word timings.

Uses POST /v1/text-to-speech/{voice_id}/with-timestamps, which returns the audio
(base64) plus character start/end times. We turn those into word timings so each
visual and caption can land on the word being spoken.
"""

import base64
import json

from . import config, http

BASE = "https://api.elevenlabs.io"


def _headers(api_key=None):
    return {"xi-api-key": api_key or config.get_key("ELEVENLABS_API_KEY"), "Accept": "application/json"}


def list_voices(api_key=None):
    try:
        res = http.request_json("GET", f"{BASE}/v2/voices?page_size=100", headers=_headers(api_key))
    except http.ApiError as e:
        if e.status != 404:
            raise
        res = http.request_json("GET", f"{BASE}/v1/voices", headers=_headers(api_key))
    return [
        {"voice_id": v["voice_id"], "name": v.get("name"), "labels": v.get("labels", {}),
         "preview_url": v.get("preview_url")}
        for v in res.get("voices", [])
    ]


def tts_with_timestamps(text, voice_id, model_id="eleven_multilingual_v2", speed=1.0,
                        stability=0.5, similarity_boost=0.75, api_key=None,
                        output_format="mp3_44100_128"):
    body = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {"stability": stability, "similarity_boost": similarity_boost, "speed": speed},
    }
    res = http.request_json(
        "POST", f"{BASE}/v1/text-to-speech/{voice_id}/with-timestamps?output_format={output_format}",
        headers=_headers(api_key), json_body=body, timeout=300,
    )
    audio = base64.b64decode(res["audio_base64"])
    alignment = res.get("normalized_alignment") or res.get("alignment")
    return audio, alignment


def words_from_alignment(alignment):
    """Group character timings into words: [{'w': 'If', 's': 0.0, 'e': 0.12}, ...]."""
    chars = alignment["characters"]
    starts = alignment["character_start_times_seconds"]
    ends = alignment["character_end_times_seconds"]
    words, cur, s, e = [], "", None, None
    for ch, cs, ce in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append({"w": cur, "s": round(s, 3), "e": round(e, 3)})
            cur, s, e = "", None, None
            continue
        if not cur:
            s = cs
        cur += ch
        e = ce
    if cur:
        words.append({"w": cur, "s": round(s, 3), "e": round(e, 3)})
    return words


def make_voice(project, data, voice_id=None):
    v = data.get("voice", {})
    voice_id = voice_id or v.get("voice_id")
    if not voice_id:
        raise ValueError("No voice_id. Run `voices` to pick one, then pass --voice-id or set voice.voice_id.")
    text = " ".join(l["text"].strip() for l in data["lines"])
    audio, alignment = tts_with_timestamps(
        text, voice_id, model_id=v.get("model_id", "eleven_multilingual_v2"),
        speed=v.get("speed", 1.0), stability=v.get("stability", 0.5),
        similarity_boost=v.get("similarity_boost", 0.75),
    )
    audio_path = project.path("audio", "voice.mp3")
    audio_path.write_bytes(audio)
    project.path("timing", "alignment.json").write_text(json.dumps(alignment))
    words = words_from_alignment(alignment)
    project.words_file().write_text(json.dumps(words, indent=1))
    return audio_path, words, len(text)
