"""Cost ledger and budget guard.

Rules:
  * Nothing paid runs without an approved amount (approve_usd) given by the viewer.
  * The estimate for the batch must not exceed the approved amount.
  * Spent + estimate must not exceed the video's budget cap.
Every estimate and spend is appended to projects/<slug>/ledger.jsonl.
"""

import json
import math
import time


class BudgetError(RuntimeError):
    pass


def append(project, kind, provider, item, usd, **extra):
    entry = {
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "kind": kind,            # estimate | spend | refund | note
        "provider": provider,
        "item": item,
        "usd": round(float(usd), 4),
    }
    entry.update(extra)
    project.dir.mkdir(parents=True, exist_ok=True)
    with project.ledger_path.open("a") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def entries(project):
    if not project.ledger_path.exists():
        return []
    return [json.loads(l) for l in project.ledger_path.read_text().splitlines() if l.strip()]


def spent(project):
    total = 0.0
    for e in entries(project):
        if e["kind"] == "spend":
            total += e["usd"]
        elif e["kind"] == "refund":
            total -= e["usd"]
    return round(total, 4)


def cents_up(usd):
    """Round a dollar amount UP to the cent, so an approval of the printed figure always covers it."""
    return math.ceil(round(float(usd) * 100, 6)) / 100


def guard(project, data, estimate_usd, approve_usd):
    """Raise BudgetError unless this spend is approved and within the cap."""
    cap = float(data.get("budget", {}).get("cap_usd", 0))
    already = spent(project)
    if approve_usd is None:
        raise BudgetError(
            f"Estimated cost is ${cents_up(estimate_usd):.2f}. Ask the viewer, then re-run with "
            f"--approve-usd {cents_up(estimate_usd):.2f} (or more) once they say yes."
        )
    if estimate_usd > float(approve_usd) + 1e-9:
        raise BudgetError(
            f"Estimate ${cents_up(estimate_usd):.2f} is more than the approved ${float(approve_usd):.2f}. "
            "Ask the viewer to approve the new amount."
        )
    if cap and already + estimate_usd > cap + 1e-9:
        raise BudgetError(
            f"This would take the video to ${already + estimate_usd:.2f}, over its "
            f"${cap:.2f} cap (already spent ${already:.2f}). Raise budget.cap_usd in "
            "video.json only if the viewer agrees."
        )
    return True


def summary(project, data):
    cap = float(data.get("budget", {}).get("cap_usd", 0))
    rows = entries(project)
    lines = [f"Spent: ${spent(project):.2f} of ${cap:.2f} cap"]
    for e in rows[-15:]:
        if e["kind"] in ("spend", "refund"):
            lines.append(f"  {e['time']}  {e['kind']:6s} {e['provider']:11s} {e['item']:10s} ${e['usd']:.3f}")
    return "\n".join(lines)


def breakdown(project):
    """Every paid item: how many times it was paid for, total, model, seconds, $/s.
    Shows where money went on remakes."""
    state = project.load_state() if project.state_path.exists() else {"clips": {}}
    per = {}
    for e in entries(project):
        if e["kind"] != "spend":
            continue
        rec = per.setdefault(e["item"], {"times": 0, "usd": 0.0, "provider": e["provider"], "first": e["time"]})
        rec["times"] += 1
        rec["usd"] += e["usd"]
    lines = ["item   paid  total    provider    model        secs   $/sec"]
    first_time_total, remake_total = 0.0, 0.0
    for item in sorted(per):
        r = per[item]
        clip = state.get("clips", {}).get(item, {})
        model = clip.get("model", "-")
        secs = (clip.get("body") or {}).get("duration")
        rate = f"{r['usd'] / r['times'] / secs:.4f}" if secs else "-"
        lines.append(f"{item:6s} {r['times']:>3}x  ${r['usd']:6.3f}  {r['provider']:10s}  {model:11s}  "
                     f"{secs if secs else '-':>4}   {rate}")
        avg = r["usd"] / r["times"]
        first_time_total += avg
        remake_total += r["usd"] - avg
    total = first_time_total + remake_total
    lines.append(f"TOTAL ${total:.2f} = ${first_time_total:.2f} first attempts + ${remake_total:.2f} remakes "
                 f"({sum(r['times'] for r in per.values())} paid generations for {len(per)} items)")
    return "\n".join(lines)


def observed_rate(project, model):
    """Average $/second actually charged for a model in this project, or None."""
    if not project.state_path.exists():
        return None
    clips = project.load_state().get("clips", {})
    paid, secs = 0.0, 0.0
    for e in entries(project):
        c = clips.get(e["item"], {})
        if e["kind"] == "spend" and e["provider"] == "higgsfield" and c.get("model") == model:
            d = (c.get("body") or {}).get("duration")
            if d:
                paid += e["usd"]
                secs += d
    return round(paid / secs, 4) if secs else None
