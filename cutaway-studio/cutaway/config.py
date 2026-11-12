"""Paths, settings and API keys.

Keys are read from environment variables first, then from ~/.cutaway/keys.env
(KEY=VALUE lines). Keys are never printed or written to project files.
"""

import os
from pathlib import Path

STUDIO_DIR = Path(__file__).resolve().parent.parent
PROJECTS_DIR = Path(os.environ.get("CUTAWAY_PROJECTS", STUDIO_DIR / "projects"))
HOME_DIR = Path(os.environ.get("CUTAWAY_HOME", Path.home() / ".cutaway"))

KEY_NAMES = (
    "HF_KEY",                # one combined "keyid:secret" value (Higgsfield's own format), or:
    "HF_API_KEY_ID",
    "HF_API_KEY_SECRET",
    "ELEVENLABS_API_KEY",
    "GEMINI_API_KEY",
)

# Defaults that a project's video.json can override.
DEFAULTS = {
    "words_per_minute": 230,          # their videos run at roughly 200-245 wpm
    "flow_daily_limit": 20,           # replaced by the real number once Flow says "limit reached"
    "gemini_image_model": "gemini-3-pro-image-preview",
    "gemini_usd_per_image": 0.15,     # conservative planning figure; check current Gemini pricing
    "caption_font": "Arial Black",
    "caption_size": 96,
    "caption_uppercase": True,
    "video_width": 1080,
    "video_height": 1920,
    "fps": 30,
    "end_hold_seconds": 0.8,
}


class MissingKey(RuntimeError):
    pass


def _read_keys_file():
    path = HOME_DIR / "keys.env"
    values = {}
    if path.exists():
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, value = line.split("=", 1)
            values[name.strip()] = value.strip().strip('"').strip("'")
    return values


def get_key(name):
    value = os.environ.get(name)
    if not value:
        value = _read_keys_file().get(name)
    if not value:
        raise MissingKey(
            f"{name} is not set. Add it as an environment variable or as a line "
            f"'{name}=...' in {HOME_DIR / 'keys.env'} (never paste keys into chat)."
        )
    return value


def has_key(name):
    try:
        get_key(name)
        return True
    except MissingKey:
        return False


def ensure_home():
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    return HOME_DIR
