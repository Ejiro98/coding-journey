"""Assemble the final vertical video with ffmpeg.

For each clip segment: use the generated clip (fitted to the segment by a gentle
speed change, a trim, or holding the last frame). If a clip doesn't exist yet,
use its start frame with a slow push-in, so a free DRAFT can be watched before any
money is spent. Then add the voice, sound effects and one-word captions.
"""

import json
import re
import shutil
import subprocess

from . import timing
from .project import frame_map

CAPTION_CLEAN = re.compile(r"[^\w'’!?-]+")


def _run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {' '.join(cmd[:6])}…\n{proc.stderr[-1500:]}")
    return proc


def probe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True,
    ).stdout.strip()
    return float(out) if out else 0.0


def _fit_filter(clip_secs, seg_secs, w, h, fps):
    base = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},fps={fps}"
    ratio = seg_secs / clip_secs if clip_secs else 1.0
    if 0.8 <= ratio <= 1.25:
        return f"setpts={ratio:.5f}*PTS,{base}"
    if ratio < 0.8:  # clip much longer than its words: speed up a little, then trim
        return f"setpts=0.8*PTS,{base}"
    # clip much shorter: slow to 1.25x, then hold the last frame
    hold = seg_secs - clip_secs * 1.25
    return f"setpts=1.25*PTS,{base},tpad=stop_mode=clone:stop_duration={max(hold, 0):.3f}"


def _segment_from_clip(src, dst, seg_secs, w, h, fps):
    vf = _fit_filter(probe_duration(src), seg_secs, w, h, fps)
    _run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vf", vf, "-t", f"{seg_secs:.3f}", "-an",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(dst)])


def _segment_from_still(img, dst, seg_secs, w, h, fps):
    frames = max(int(round(seg_secs * fps)), 1)
    vf = (f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,crop={w * 2}:{h * 2},"
          f"zoompan=z='min(1+0.10*on/{frames},1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
          f":d=1:s={w}x{h}:fps={fps}")
    _run(["ffmpeg", "-y", "-v", "error", "-loop", "1", "-framerate", str(fps), "-i", str(img),
          "-vf", vf, "-frames:v", str(frames), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
          "-pix_fmt", "yuv420p", str(dst)])


def _placeholder(dst, seg_secs, w, h, fps, label):
    base = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
            f"color=c=0x1d2533:s={w}x{h}:r={fps}:d={seg_secs:.3f}"]
    tail = ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(dst)]
    try:
        _run(base + ["-vf", f"drawtext=text='{label}':fontcolor=white:fontsize=64:"
                            "x=(w-text_w)/2:y=(h-text_h)/2"] + tail)
    except RuntimeError:  # no font available for drawtext: plain card
        _run(base + tail)


def _ass_time(t):
    t = max(t, 0)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def captions_ass(words, w, h, font, size, upper=True):
    """One word at a time, centred a little below the middle (like their videos)."""
    head = (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {w}\nPlayResY: {h}\nWrapStyle: 2\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        f"Style: Word,{font},{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,"
        f"-1,0,0,0,100,100,0,0,1,7,3,2,60,60,{int(h * 0.36)},1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    )
    events = []
    for i, wd in enumerate(words):
        text = CAPTION_CLEAN.sub("", wd["w"]).strip("-")
        if not text:
            continue
        end = words[i + 1]["s"] if i + 1 < len(words) else wd["e"] + 0.4
        end = max(end, wd["s"] + 0.08)
        events.append(f"Dialogue: 0,{_ass_time(wd['s'])},{_ass_time(end)},Word,,0,0,0,,"
                      f"{text.upper() if upper else text}")
    return head + "\n".join(events) + "\n"


def assemble(project, data, draft=False, log=print):
    w, h, fps = (project.setting(data, k) for k in ("video_width", "video_height", "fps"))
    words, source = timing.load_words(project, data, project.setting(data, "words_per_minute"))
    segs, total = timing.segments(data, words, project.setting(data, "end_hold_seconds"))
    build = project.dir / "build"
    if build.exists():
        shutil.rmtree(build)
    build.mkdir(parents=True)
    frames = frame_map(data)
    clips = {c["id"]: c for c in data["clips"]}
    used = {"clip": 0, "still": 0, "missing": 0}
    parts = []
    for i, seg in enumerate(segs):
        out = build / f"seg{i:03d}.mp4"
        clip = clips[seg["clip"]]
        cfile = None if draft else project.clip_file(clip["id"])
        if cfile:
            _segment_from_clip(cfile, out, seg["seconds"], w, h, fps)
            used["clip"] += 1
        elif project.frame_file(clip["from"]):
            _segment_from_still(project.frame_file(clip["from"]), out, seg["seconds"], w, h, fps)
            used["still"] += 1
        else:
            _placeholder(out, seg["seconds"], w, h, fps, f"{clip['id']} needs {clip['from']}")
            used["missing"] += 1
        parts.append(out)
    concat = build / "concat.txt"
    concat.write_text("".join(f"file '{p.name}'\n" for p in parts))
    silent = build / "video.mp4"
    _run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(silent)])

    ass = build / "captions.ass"
    ass.write_text(captions_ass(words, w, h, project.setting(data, "caption_font"),
                                project.setting(data, "caption_size"), project.setting(data, "caption_uppercase")))

    inputs = ["-i", str(silent)]
    voice = project.voice_file()
    filters, mix = [], []
    idx = 1
    if voice:
        inputs += ["-i", str(voice)]
        mix.append(f"[{idx}:a]")
        idx += 1
    lt = timing.line_times(data, words)
    for sfx in data.get("sfx", []):
        f = project.dir / sfx["file"]
        if not f.exists():
            log(f"sound effect missing, skipped: {sfx['file']}")
            continue
        at = _sfx_time(sfx, lt)
        inputs += ["-i", str(f)]
        filters.append(f"[{idx}:a]volume={sfx.get('gain_db', -10)}dB,adelay={int(at * 1000)}:all=1[s{idx}]")
        mix.append(f"[s{idx}]")
        idx += 1
    music = data.get("music")
    if music and (project.dir / music["file"]).exists():
        inputs += ["-stream_loop", "-1", "-i", str(project.dir / music["file"])]
        filters.append(f"[{idx}:a]volume={music.get('gain_db', -18)}dB[m]")
        mix.append("[m]")
        idx += 1

    vf = f"[0:v]subtitles={ass.name}[v]"
    if mix:
        filters.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=first[a]")
    graph = ";".join([vf] + filters)
    final = project.path("final", f"{project.slug}{'-draft' if (draft or used['clip'] < len(segs)) else ''}.mp4")
    cmd = ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", graph, "-map", "[v]"]
    if mix:
        cmd += ["-map", "[a]", "-c:a", "aac", "-b:a", "192k"]
    cmd += ["-t", f"{total:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(final)]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=build)
    if proc.returncode != 0:
        raise RuntimeError(f"final render failed:\n{proc.stderr[-1500:]}")
    report = {"file": str(final), "seconds": total, "timing": source, **used}
    (build / "report.json").write_text(json.dumps(report, indent=2))
    return report


def _sfx_time(sfx, line_times):
    lt = line_times[str(sfx["line"])]
    if sfx.get("word"):
        target = sfx["word"].lower()
        for wd in lt["words"]:
            if CAPTION_CLEAN.sub("", wd["w"]).lower() == target:
                return wd["s"] + float(sfx.get("offset", 0))
    return lt["start"] + float(sfx.get("offset", 0))
