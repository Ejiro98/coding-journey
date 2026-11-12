"""Turn word timings into line times and clip segments.

Each clip covers one or more script lines; its segment runs from the first word of
its first line to the first word of the next clip (the last one runs to the end of
the voice plus a short hold). Without a voiceover we estimate at the project's
words-per-minute so a draft can be cut before anything is paid for.
"""

import json
import re

from .project import full_text

TOKEN = re.compile(r"\S+")


def estimated_words(data, wpm=230):
    per = 60.0 / wpm
    out, t = [], 0.0
    for tok in TOKEN.findall(full_text(data)):
        dur = per * (1.6 if tok[-1] in ".!?" else 1.25 if tok[-1] in ",;:" else 1.0)
        out.append({"w": tok, "s": round(t, 3), "e": round(t + per * 0.9, 3)})
        t += dur
    return out


def load_words(project, data, wpm=230):
    path = project.words_file()
    if path.exists():
        return json.loads(path.read_text()), "voiceover"
    return estimated_words(data, wpm), "estimate"


def line_times(data, words):
    """Map script lines onto the word list by word count (TTS text = joined lines)."""
    times, i = {}, 0
    for line in data["lines"]:
        n = len(TOKEN.findall(line["text"]))
        if n == 0:
            continue
        chunk = words[i:i + n]
        if not chunk:
            raise ValueError(f"Ran out of timed words at line {line['id']}; re-run the voiceover.")
        times[str(line["id"])] = {"start": chunk[0]["s"], "end": chunk[-1]["e"], "words": chunk}
        i += n
    if i != len(words):
        # ElevenLabs can split/merge a token (e.g. "3 a.m."); tolerate a small mismatch.
        if abs(i - len(words)) > 3:
            raise ValueError(f"Script has {i} words but the voice has {len(words)}; re-run the voiceover.")
    return times


def segments(data, words, end_hold=0.8):
    lt = line_times(data, words)
    clips = data["clips"]
    total_end = words[-1]["e"] + end_hold
    segs = []
    for idx, clip in enumerate(clips):
        start = 0.0 if idx == 0 else lt[str(clip["lines"][0])]["start"]
        if idx + 1 < len(clips):
            end = lt[str(clips[idx + 1]["lines"][0])]["start"]
        else:
            end = total_end
        segs.append({"clip": clip["id"], "start": round(start, 3), "end": round(end, 3),
                     "seconds": round(end - start, 3)})
    return segs, round(total_end, 3)


def table(segs):
    rows = ["clip   start    end   secs"]
    for s in segs:
        rows.append(f"{s['clip']:5s} {s['start']:6.2f} {s['end']:6.2f} {s['seconds']:6.2f}")
    return "\n".join(rows)
