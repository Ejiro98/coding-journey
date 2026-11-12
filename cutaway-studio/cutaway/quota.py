"""Daily counter for free Google Flow images.

Flow's free Nano Banana allowance is a daily limit that changes over time, so we
count what we use and learn the real limit the first time Flow says it is reached.
"""

import json
import time

from . import config


def _path():
    return config.ensure_home() / "flow_quota.json"


def _load():
    p = _path()
    if p.exists():
        return json.loads(p.read_text())
    return {"days": {}, "learned_limit": None}


def _save(data):
    _path().write_text(json.dumps(data, indent=2) + "\n")


def today():
    return time.strftime("%Y-%m-%d")


def limit(data=None):
    data = data or _load()
    return data.get("learned_limit") or config.DEFAULTS["flow_daily_limit"]


def used(day=None):
    return _load()["days"].get(day or today(), 0)


def add(n=1):
    data = _load()
    d = today()
    data["days"][d] = data["days"].get(d, 0) + int(n)
    _save(data)
    return data["days"][d]


def limit_hit():
    """Call when Flow refuses with a daily-limit message: today's count becomes the known limit."""
    data = _load()
    count = data["days"].get(today(), 0)
    if count:
        data["learned_limit"] = count
    _save(data)
    return data["learned_limit"]


def status():
    data = _load()
    lim = limit(data)
    u = data["days"].get(today(), 0)
    source = "learned from Flow" if data.get("learned_limit") else "assumed (not yet confirmed)"
    return {"date": today(), "used": u, "limit": lim, "left": max(lim - u, 0), "limit_source": source}
