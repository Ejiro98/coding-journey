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
REGIONAL_PHRASES = {
    r"\b(a|the) lift\b": "say 'elevator' (understood everywhere; 'lift' confuses US viewers)",
    r"\bgas station\b": "fine for the US; UK says petrol station. OK if the caption covers both",
}

TARGET_WORDS = (290, 315)
HARD_WORDS = (250, 340)
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
        err(f"{total} words. Aim for {TARGET_WORDS[0]}-{TARGET_WORDS[1]} (about 75-85s, over the 60s Creator Rewards minimum).")
    elif not (TARGET_WORDS[0] <= total <= TARGET_WORDS[1]):
        warn(f"{total} words; the sweet spot is {TARGET_WORDS[0]}-{TARGET_WORDS[1]}.")
    else:
        ok(f"{total} words")

    # 4. The But/So chain
    starts = [l["text"].strip().split()[0].strip(",").lower() for l in lines if l["text"].strip()]
    buts = sum(1 for s in starts if s == "but")
    sos = sum(1 for s in starts if s == "so")
    if buts < 5 or sos < 5:
        warn(f"{buts} lines start with 'But' and {sos} with 'So'; their videos run 5-8 pairs.")
    else:
        ok(f"{buts} But / {sos} So pairs")
    for l in lines:
        role = l.get("role", "").upper()
        t = l["text"].strip().lower()
        if role.startswith("PROBLEM") and not t.startswith(("but", "and")):
            warn(f"Line {l['id']} is a PROBLEM but doesn't start with 'But'.")
        if role.startswith("FIX") and not t.startswith(("so", "that", "if", "then")):
            warn(f"Line {l['id']} is a FIX but doesn't start with 'So'.")

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
    for pattern, advice in REGIONAL_PHRASES.items():
        if re.search(pattern, text.lower()):
            warn(f"'{re.search(pattern, text.lower()).group(0)}': {advice}")

    # 8. Every part is built before it's used
    report.extend(check_build_order(data))
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
