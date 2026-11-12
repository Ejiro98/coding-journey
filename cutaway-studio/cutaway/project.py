"""Project files.

Each video lives in projects/<slug>/:
  video.json      the plan: script lines, parts, frames, clips, voice, budget (committed)
  state.json      what has been made: request ids, files, costs (not committed)
  ledger.jsonl    every estimate and spend (not committed)
  frames/ clips/ audio/ timing/ final/   generated media (not committed)
"""

import json
import re
from pathlib import Path

from . import config

MEDIA_DIRS = ("frames", "clips", "audio", "timing", "final", "build")


class ProjectError(RuntimeError):
    pass


class Project:
    def __init__(self, slug, root=None):
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug):
            raise ProjectError("slug must be lowercase letters, numbers and dashes")
        self.slug = slug
        self.dir = Path(root or config.PROJECTS_DIR) / slug
        self.video_path = self.dir / "video.json"
        self.state_path = self.dir / "state.json"
        self.ledger_path = self.dir / "ledger.jsonl"

    # ---------- plan ----------
    def exists(self):
        return self.video_path.exists()

    def load(self):
        if not self.exists():
            raise ProjectError(f"No project at {self.video_path}")
        data = json.loads(self.video_path.read_text())
        validate(data)
        return data

    def save(self, data):
        self.dir.mkdir(parents=True, exist_ok=True)
        self.video_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")

    def setting(self, data, name):
        return data.get("settings", {}).get(name, config.DEFAULTS[name])

    # ---------- state ----------
    def load_state(self):
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return {"frames": {}, "clips": {}, "voice": {}, "uploads": {}}

    def save_state(self, state):
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2) + "\n")
        tmp.replace(self.state_path)

    # ---------- paths ----------
    def path(self, *parts):
        p = self.dir.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def frame_file(self, frame_id):
        for ext in (".png", ".jpg", ".jpeg", ".webp"):
            p = self.dir / "frames" / f"{frame_id}{ext}"
            if p.exists():
                return p
        return None

    def clip_file(self, clip_id):
        p = self.dir / "clips" / f"{clip_id}.mp4"
        return p if p.exists() else None

    def voice_file(self):
        p = self.dir / "audio" / "voice.mp3"
        return p if p.exists() else None

    def words_file(self):
        return self.path("timing", "words.json")


def full_text(data):
    return " ".join(line["text"].strip() for line in data["lines"])


def line_index(data):
    return {line["id"]: i for i, line in enumerate(data["lines"])}


def frame_map(data):
    return {f["id"]: f for f in data.get("frames", [])}


def validate(data):
    """Catch plan mistakes early, before anything is generated."""
    for key in ("slug", "lines"):
        if key not in data:
            raise ProjectError(f"video.json is missing '{key}'")
    ids = [str(line.get("id")) for line in data["lines"]]
    if len(set(ids)) != len(ids):
        raise ProjectError("line ids must be unique")
    known_lines = set(ids)
    frames = frame_map(data)
    for f in data.get("frames", []):
        for ref in f.get("refs", []):
            if ref not in frames:
                raise ProjectError(f"frame {f['id']} refers to unknown frame {ref}")
        if f.get("state") is not None and str(f["state"]) not in known_lines:
            raise ProjectError(f"frame {f['id']} has unknown state line {f['state']}")
    covered = []
    prev_last = None
    for clip in data.get("clips", []):
        if clip.get("from") not in frames:
            raise ProjectError(f"clip {clip.get('id')} starts from unknown frame {clip.get('from')}")
        if clip.get("to") and clip["to"] not in frames:
            raise ProjectError(f"clip {clip['id']} ends on unknown frame {clip['to']}")
        lines = [str(l) for l in clip.get("lines", [])]
        if not lines:
            raise ProjectError(f"clip {clip['id']} has no lines")
        # A second clip on the same line is allowed when it starts on a cue word.
        if lines[0] == prev_last and clip.get("cue"):
            lines = lines[1:]
        for lid in lines:
            if lid not in known_lines:
                raise ProjectError(f"clip {clip['id']} uses unknown line {lid}")
            covered.append(lid)
        prev_last = str(clip["lines"][-1])
    if data.get("clips"):
        if covered != ids:
            raise ProjectError(
                "clips must cover every script line exactly once, in order. "
                f"Lines: {ids}  Covered: {covered}"
            )
    return True
