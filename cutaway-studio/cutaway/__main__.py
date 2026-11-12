"""Cutaway Studio command line. Run from the cutaway-studio folder:

    python3 -m cutaway <command> [options]

Stages (each needs the viewer's approval before the next paid step):
  lint      check the script against the formula
  voice     ElevenLabs voiceover + word timings        (approval: voice)
  timing    show how long each clip must be
  frames    keyframes: Flow prompts / import, or paid fallbacks   (approval: frames)
  clips     Higgsfield clips: estimate, then run with --approve-usd  (approval: spend)
  assemble  draft (free, from stills) or final MP4
"""

import argparse
import json
import sys
from pathlib import Path

from . import assemble as asm, clips as clp, frames as frm, higgsfield as hf, ledger, lint, quota, timing
from .project import Project, ProjectError


def cmd_lint(p, args):
    data = p.load()
    report = lint.check(data)
    print(lint.format_report(report))
    return 1 if lint.has_errors(report) else 0


def cmd_status(p, args):
    data = p.load()
    st = p.load_state()
    frames = data.get("frames", [])
    clips = data.get("clips", [])
    fdone = [f["id"] for f in frames if p.frame_file(f["id"])]
    cdone = [c["id"] for c in clips if p.clip_file(c["id"])]
    words, source = timing.load_words(p, data, p.setting(data, "words_per_minute"))
    _, total = timing.segments(data, words, p.setting(data, "end_hold_seconds")) if clips else (None, 0)
    print(f"Project: {p.slug}  ({data.get('title', '')})")
    print(f"Script : {len(lint.words(' '.join(l['text'] for l in data['lines'])))} words, "
          f"{'errors' if lint.has_errors(lint.check(data)) else 'passes checks'}")
    print(f"Voice  : {'done' if p.voice_file() else 'not made'} (timing from {source}, ~{total:.1f}s)")
    print(f"Frames : {len(fdone)}/{len(frames)} made" + (f"  next: {next((f['id'] for f in frames if f['id'] not in fdone), '-')}" if len(fdone) < len(frames) else ""))
    print(f"Clips  : {len(cdone)}/{len(clips)} made")
    q = quota.status()
    print(f"Flow   : {q['used']}/{q['limit']} free images used today ({q['limit_source']})")
    print(ledger.summary(p, data))
    finals = sorted((p.dir / "final").glob("*.mp4")) if (p.dir / "final").exists() else []
    if finals:
        print("Output : " + ", ".join(str(f) for f in finals))
    return 0


def cmd_voices(args):
    from . import elevenlabs as el
    for v in el.list_voices():
        labels = ", ".join(f"{k}: {val}" for k, val in v["labels"].items())
        print(f"{v['voice_id']}  {v['name']}  ({labels})")
    return 0


def cmd_voice(p, args):
    from . import elevenlabs as el
    data = p.load()
    report = lint.check(data)
    if lint.has_errors(report) and not args.force:
        print(lint.format_report(report))
        print("\nFix the script errors first (or --force).")
        return 1
    path, words, chars = el.make_voice(p, data, args.voice_id)
    if args.voice_id and data["voice"].get("voice_id") != args.voice_id:
        data["voice"]["voice_id"] = args.voice_id
        p.save(data)
    ledger.append(p, "note", "elevenlabs", "voice", 0, characters=chars)
    secs = words[-1]["e"]
    print(f"Voiceover: {path}  ({secs:.1f}s, {len(words)} words, {chars} characters, "
          f"{len(words) / secs * 60:.0f} wpm)")
    return 0


def cmd_timing(p, args):
    data = p.load()
    words, source = timing.load_words(p, data, p.setting(data, "words_per_minute"))
    segs, total = timing.segments(data, words, p.setting(data, "end_hold_seconds"))
    model = args.model or data.get("video", {}).get("model", "wan3")
    print(f"Timing from {source}; total {total:.1f}s; model {model}")
    print(timing.table(segs))
    reqs = [(c, s["seconds"], model) for c, s in zip(data["clips"], segs)]
    plan, unknown = clp.planning_total(reqs)
    print(f"Planning cost for all clips on {model}: ~${plan:.2f}" + (f" (+ {len(unknown)} unpriced)" if unknown else ""))
    return 0


def cmd_frames(p, args):
    data = p.load()
    if args.action == "prompts":
        q = quota.status()
        print(f"Flow free images today: {q['used']}/{q['limit']} used, {q['left']} left ({q['limit_source']})\n")
        for item in frm.plan(p, data):
            if item["done"] and not args.all:
                continue
            state = "DONE" if item["done"] else ("READY" if item["ready"] else f"WAITING for {', '.join(item['waiting_for'])}")
            print(f"== {item['id']}  [{state}]")
            if item["refs"] or item["waiting_for"]:
                print(f"attach as references: {item['refs'] + [f'{w} (not made yet)' for w in item['waiting_for']]}")
            else:
                print("attach as references: none (first frame)")
            print(item["prompt"] + "\n")
        return 0
    if args.action == "import":
        dest = frm.import_frame(p, args.frame, Path(args.file).expanduser(), source=args.source)
        print(f"{args.frame} -> {dest}" + ("  (+1 Flow image today)" if args.source == "flow" else ""))
        return 0
    if args.action == "gemini":
        print(frm.make_with_gemini(p, data, args.frame, args.approve_usd))
        return 0
    if args.action == "higgsfield":
        print(frm.make_with_higgsfield(p, data, args.frame, args.approve_usd))
        return 0
    return 2


def cmd_clips(p, args):
    data = p.load()
    client = hf.Client()
    if args.action == "estimate":
        rows, total = clp.estimate(p, data, client, args.model, args.only)
        for r in rows:
            print(f"{r['clip']}: {r['seconds']}s on {r['model']}  ${r['usd']:.3f}")
        print(f"TOTAL ${total:.2f}  (spent so far ${ledger.spent(p):.2f}, cap ${data['budget']['cap_usd']:.2f})")
        return 0
    made = clp.run(p, data, client, args.approve_usd, args.model, args.only)
    print(f"Made {len(made)} clip(s). {ledger.summary(p, data)}")
    return 0


def cmd_assemble(p, args):
    data = p.load()
    rep = asm.assemble(p, data, draft=args.draft)
    print(json.dumps(rep, indent=2))
    return 0


def run_checks(log=print):
    """Free checks: tools installed and every key accepted. Spends nothing."""
    import shutil
    import uuid
    from . import config, http
    ok = True

    def line(good, name, msg):
        nonlocal ok
        ok = ok and good is not False
        mark = "OK  " if good else ("--  " if good is None else "FAIL")
        log(f"[{mark}] {name}: {msg}")

    v = sys.version_info
    line(v >= (3, 9), "Python", f"{v.major}.{v.minor}" + ("" if v >= (3, 9) else " (need 3.9+: brew install python)"))
    if shutil.which("ffmpeg"):
        import subprocess
        filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        has_subs = " subtitles " in filters
        line(has_subs, "ffmpeg", "installed, can burn in captions" if has_subs else
             "installed but without libass (captions): brew reinstall ffmpeg")
    else:
        line(False, "ffmpeg", "missing: brew install ffmpeg")
    try:
        hf.credentials()
        hf_found = True
        line(True, "Higgsfield key", "found (HF_KEY)" if config.has_key("HF_KEY") else "found (ID + secret)")
    except config.MissingKey as e:
        hf_found = False
        line(False, "Higgsfield key", "not set. Add HF_KEY=keyid:secret (or HF_API_KEY_ID and HF_API_KEY_SECRET)"
             if "HF_KEY should" not in str(e) else str(e))
    for name, optional in (("ELEVENLABS_API_KEY", False), ("GEMINI_API_KEY", True)):
        present = config.has_key(name)
        line(present or (None if optional else False), name, "found" if present else ("not set (optional)" if optional else "not set"))

    if hf_found:
        try:
            c = hf.Client()
            http.request("GET", f"{hf.BASE}/requests/{uuid.uuid4()}/status", headers=c._auth(), retries=1)
            line(True, "Higgsfield", "key accepted")
        except http.ApiError as e:
            if e.status == 404:
                line(True, "Higgsfield", "key accepted")
            elif e.status == 401:
                line(False, "Higgsfield", "key ID or secret rejected (401). Re-copy both from the console.")
            else:
                line(False, "Higgsfield", f"unexpected reply {e.status}: {e.detail}")
    if config.has_key("ELEVENLABS_API_KEY"):
        try:
            sub = http.request_json("GET", "https://api.elevenlabs.io/v1/user/subscription",
                                    headers={"xi-api-key": config.get_key("ELEVENLABS_API_KEY")}, retries=1)
            left = sub.get("character_limit", 0) - sub.get("character_count", 0)
            line(True, "ElevenLabs", f"key accepted, plan '{sub.get('tier')}', {left:,} characters left "
                                     f"(~{left // 1700} videos)")
        except http.ApiError as e:
            if e.status == 401:
                line(False, "ElevenLabs", "key rejected (401). Re-copy it from your ElevenLabs profile.")
            else:
                line(None, "ElevenLabs", f"couldn't read plan ({e.status}); the key may lack 'user' permission")
    if config.has_key("GEMINI_API_KEY"):
        try:
            http.request("GET", "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1",
                         headers={"x-goog-api-key": config.get_key("GEMINI_API_KEY")}, retries=1)
            line(True, "Gemini", "key accepted")
        except http.ApiError as e:
            line(False, "Gemini", f"key rejected ({e.status})")
    log("\nAll set." if ok else "\nFix the FAIL lines above, then run check again.")
    return ok


def cmd_check(args):
    return 0 if run_checks() else 1


def cmd_quota(args):
    if args.action == "add":
        quota.add(args.n)
    elif args.action == "limit-hit":
        quota.limit_hit()
    print(json.dumps(quota.status(), indent=2))
    return 0


def cmd_ledger(p, args):
    print(ledger.summary(p, p.load()))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="cutaway", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def with_slug(name, help_):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("slug")
        return sp

    with_slug("lint", "check the script")
    with_slug("status", "where a video is up to")
    with_slug("ledger", "costs so far")
    sub.add_parser("voices", help="list ElevenLabs voices")
    sub.add_parser("check", help="free check that tools and keys work (spends nothing)")
    sp = with_slug("voice", "make the voiceover with word timings")
    sp.add_argument("--voice-id")
    sp.add_argument("--force", action="store_true")
    sp = with_slug("timing", "clip lengths from the voice")
    sp.add_argument("--model")
    sp = sub.add_parser("frames", help="keyframes")
    sp.add_argument("action", choices=["prompts", "import", "gemini", "higgsfield"])
    sp.add_argument("slug")
    sp.add_argument("frame", nargs="?")
    sp.add_argument("file", nargs="?")
    sp.add_argument("--source", default="flow")
    sp.add_argument("--approve-usd", type=float)
    sp.add_argument("--all", action="store_true")
    sp = sub.add_parser("clips", help="Higgsfield clips")
    sp.add_argument("action", choices=["estimate", "run"])
    sp.add_argument("slug")
    sp.add_argument("--model", choices=sorted(hf.VIDEO_MODELS))
    sp.add_argument("--only", help="comma-separated clip ids, e.g. C01,C02")
    sp.add_argument("--approve-usd", type=float)
    sp = with_slug("assemble", "build the MP4")
    sp.add_argument("--draft", action="store_true", help="ignore clips; stills only (free preview)")
    sp = sub.add_parser("quota", help="Flow free-image counter")
    sp.add_argument("action", choices=["status", "add", "limit-hit"], nargs="?", default="status")
    sp.add_argument("n", nargs="?", type=int, default=1)

    args = ap.parse_args(argv)
    try:
        if args.cmd == "voices":
            return cmd_voices(args)
        if args.cmd == "check":
            return cmd_check(args)
        if args.cmd == "quota":
            return cmd_quota(args)
        p = Project(args.slug)
        return {
            "lint": cmd_lint, "status": cmd_status, "ledger": cmd_ledger, "voice": cmd_voice,
            "timing": cmd_timing, "frames": cmd_frames, "clips": cmd_clips, "assemble": cmd_assemble,
        }[args.cmd](p, args)
    except (ProjectError, ledger.BudgetError, ValueError) as e:
        print(f"Stopped: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
