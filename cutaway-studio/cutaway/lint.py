"""Script checks, built from 9 viral cutaway videos (see README).

Errors stop the pipeline; warnings are shown for the viewer to decide.
"""

import re

WORD_RE = re.compile(r"[A-Za-z0-9']+")

# Words that read differently to US and UK viewers, or slow the hook down.
REGIONAL = {
    "tarmac": "say 'road' or 'asphalt' (Americans don't say tarmac)",
    "pavement": "means the road in the US but the footpath in the UK; say 'sidewalk' or 'footpath' carefully",
    "sidewalk": "UK viewers say 'pavement'; consider 'path'",
    "petrol": "say 'fuel' (Americans say gas)",
    "lorry": "say 'truck'",
    "flat": None,  # too common as an adjective to flag automatically
    "bin": None,
}
# Words most viewers don't use day to day; their scripts say leaks, drips, runs, soaks.
UNCOMMON = {
    "seep": "say 'leak', 'drip' or 'soak'", "seeps": "say 'leaks', 'drips' or 'soaks'",
    "seeping": "say 'leaking' or 'soaking'", "percolate": "say 'soak through'",
    "percolates": "say 'soaks through'", "aquifer": "say 'the water underground'",
    "subterranean": "say 'underground'", "utilize": "say 'use'", "commence": "say 'start'",
    "approximately": "say 'about'", "facilitate": "say 'help'",
}

REGIONAL_PHRASES = {
    r"\b(a|the) lift\b": "say 'elevator' (understood everywhere; 'lift' confuses US viewers)",
    r"\bgas station\b": "fine for the US; UK says petrol station. OK if the caption covers both",
}

TARGET_WORDS = (250, 300)   # their videos: 235-327 words, newest 235-287
HARD_WORDS = (230, 330)
HOOK_MAX_WORDS_WARN = 16
HOOK_MAX_WORDS_ERROR = 18


def words(text):
    return WORD_RE.findall(text)


def _norm(text):
    return " " + re.sub(r"[^a-z0-9' ]+", " ", text.lower()) + " "


def check(data):
    """Return a list of (level, message). level is 'error' or 'warn' or 'ok'."""
    lines = data["lines"]
    text = " ".join(l["text"].strip() for l in lines)
    report = []

    def err(m):
        report.append(("error", m))

    def warn(m):
        report.append(("warn", m))

    def ok(m):
        report.append(("ok", m))

    # 1. Hook opening
    first = lines[0]["text"].strip()
    if not re.match(r"(?i)^(if you|what if you)\b", first):
        err("The first line must open with 'If you…' (their hits all do; story openings flopped).")
    else:
        ok("Opens with 'If you…'")
    first_sentence = re.split(r"(?<=[.!?])\s", first)[0].lower()
    if not re.search(r"\byou (have|now have|'ve|have now)\b|\byou've\b|\byou've now\b", first_sentence):
        warn("First sentence should name the topic: '…, you have a [thing].'")

    # 2. Time to the first "But"
    all_words = words(text)
    lower = [w.lower() for w in all_words]
    if "but" not in lower:
        err("No 'But' anywhere: the chain needs problems.")
    else:
        n = lower.index("but")
        if n > HOOK_MAX_WORDS_ERROR:
            err(f"First 'But' comes after {n} words (~{n / 230 * 60:.1f}s). Keep it within 16 words (~3.5s).")
        elif n > HOOK_MAX_WORDS_WARN:
            warn(f"First 'But' comes after {n} words (~{n / 230 * 60:.1f}s); their biggest hits did it in 13-17.")
        else:
            ok(f"First 'But' after {n} words (~{n / 230 * 60:.1f}s)")

    # 3. Length
    total = len(all_words)
    if not (HARD_WORDS[0] <= total <= HARD_WORDS[1]):
        err(f"{total} words. Aim for {TARGET_WORDS[0]}-{TARGET_WORDS[1]} (about 65-80s, over the 60s Creator Rewards minimum).")
    elif not (TARGET_WORDS[0] <= total <= TARGET_WORDS[1]):
        warn(f"{total} words; the sweet spot is {TARGET_WORDS[0]}-{TARGET_WORDS[1]}.")
    else:
        ok(f"{total} words")

    # 4. The But/So chain
    problems = [l for l in lines if l.get("role", "").upper().startswith("PROBLEM")]
    fixes = [l for l in lines if l.get("role", "").upper().startswith("FIX")]
    if len(problems) < 4 or len(fixes) < 4:
        warn(f"{len(problems)} problems and {len(fixes)} fixes; their videos run 5-8 problem/fix pairs.")
    else:
        ok(f"{len(problems)} problems / {len(fixes)} fix lines")
    for l in problems:
        if not l["text"].strip().lower().startswith(("but", "and")):
            warn(f"Line {l['id']} is a PROBLEM but doesn't start with 'But'.")
    # Fixes may start "So you…", or with a plain verb ("Give it a slope", "Add a pump") like theirs.

    # 5. Ending
    if not any("congratulations" in l["text"].lower() for l in lines[-3:]):
        warn("End with 'Congratulations! You've built…' (every hit does).")
    else:
        ok("Congratulations ending")

    # 6. Sentence length
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    long = [s for s in sentences if len(words(s)) > 24]
    for s in long:
        warn(f"Long sentence ({len(words(s))} words), hard to follow at speed: \"{s[:70]}…\"")

    # 7. Regional words
    norm = _norm(text)
    for word, advice in REGIONAL.items():
        if advice and f" {word} " in norm:
            warn(f"'{word}': {advice}")
    for word, advice in UNCOMMON.items():
        if f" {word} " in norm:
            warn(f"'{word}' isn't an everyday word: {advice}")
    for pattern, advice in REGIONAL_PHRASES.items():
        if re.search(pattern, text.lower()):
            warn(f"'{re.search(pattern, text.lower()).group(0)}': {advice}")

    # 8. Every part is built before it's used
    report.extend(check_build_order(data))
    # 9. Shots follow their animation method
    report.extend(check_shots(data))
    return report


MOVES = ("dolly-in", "pull-back", "pan", "follow")


def check_shots(data):
    """Their method (measured): ~3 s beats, one change per clip, camera locked for most
    clips, moves only moderate (about 2x closer, or following the object), back to the
    master view. Big jumps in one clip make the model cut instead of moving."""
    report = []
    frames = {f["id"]: f for f in data.get("frames", [])}
    clips = data.get("clips", [])
    if not clips:
        return report
    if frames and not all("view" in f for f in frames.values()):
        report.append(("warn", "Frames have no 'view'/'zoom', so camera moves can't be checked."))
        return report
    for f in frames.values():
        if f.get("refs") and float(f.get("zoom", 1)) < 1:
            report.append(("warn", f"Frame {f['id']} pulls back wider than its reference. Image edit models can't "
                                   "show what was outside the old picture and invent a new place (landfill L10). "
                                   "Keep the framing, or make the wide still first and zoom IN from it."))
    run = 0
    for c in clips:
        a, b = frames.get(c["from"], {}), frames.get(c.get("to") or "", {})
        moving = bool(b) and a.get("view") != b.get("view")
        if moving:
            za, zb = float(a.get("zoom", 1)), float(b.get("zoom", 1))
            ratio = max(za, zb) / max(min(za, zb), 0.01)
            if c.get("move") not in MOVES:
                report.append(("error", f"Clip {c['id']} changes view ({a.get('view')} -> {b.get('view')}) "
                                        f"but has no 'move' ({', '.join(MOVES)})."))
            if ratio > 2.2:
                report.append(("error", f"Clip {c['id']} zooms {ratio:.1f}x in one clip; models cut instead "
                                        "of moving. Add an in-between frame (keep moves to about 2x)."))
            run += 1
            if run == 3:
                report.append(("warn", f"Three camera moves in a row ending at {c['id']}; their camera "
                                       "settles on a view for several beats."))
        else:
            run = 0
        m = c.get("motion", "")
        if len(words(m)) > 45 or m.lower().count(" then ") > 1:
            report.append(("warn", f"Clip {c['id']} motion is long ({len(words(m))} words); "
                                   "their clips show ONE change each."))
        if not c.get("to") and not c.get("hold"):
            report.append(("warn", f"Clip {c['id']} has no end still ('to'), so the model decides where it ends "
                                   "and every later clip inherits it. Stills cost cents, clips cost dollars: add "
                                   "an end still, or mark \"hold\": true if nothing new stays on screen after it "
                                   "(wind, rain running off, people walking)."))
    try:
        from . import timing
        segs, _ = timing.segments(data, timing.estimated_words(data, 230), 0.8)
        for sg in segs:
            if sg["seconds"] > 7.5:
                report.append(("warn", f"Clip {sg['clip']} runs ~{sg['seconds']:.1f}s; their beats are ~3-4 s. "
                                       "Split the line into two clips (use a cue word)."))
    except ValueError as e:
        report.append(("error", str(e)))
    if not any(lvl == "error" for lvl, _ in report):
        report.append(("ok", "Shots follow the method (moderate moves, one change per clip)"))
    return report


def check_build_order(data):
    report = []
    parts = data.get("parts", {})
    if not parts:
        return [("warn", "No 'parts' listed, so build-before-use can't be checked.")]
    order = [str(l["id"]) for l in data["lines"]]
    for name, spec in parts.items():
        built = str(spec["built_in"])
        if built not in order:
            report.append(("error", f"Part '{name}' is built in unknown line {built}."))
            continue
        aliases = spec.get("aliases") or [name]
        for l in data["lines"][: order.index(built)]:
            low = _norm(l["text"])
            for a in aliases:
                if f" {a.lower()} " in low:
                    report.append((
                        "error",
                        f"Line {l['id']} mentions '{a}' before it is built (line {built}). "
                        "Add a problem + 'So…' that introduces it first, or move it.",
                    ))
                    break
    if not any(level == "error" for level, _ in report):
        report.append(("ok", f"All {len(parts)} parts are built before they are used"))
    return report


def has_errors(report):
    return any(level == "error" for level, _ in report)


def format_report(report):
    icon = {"ok": "  ok  ", "warn": " WARN ", "error": "ERROR "}
    return "\n".join(f"[{icon[level]}] {msg}" for level, msg in report)
