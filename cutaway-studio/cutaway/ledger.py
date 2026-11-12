"""Cost ledger and budget guard.

Rules:
  * Nothing paid runs without an approved amount (approve_usd) given by the viewer.
  * The estimate for the batch must not exceed the approved amount.
  * Spent + estimate must not exceed the video's budget cap.
Every estimate and spend is appended to projects/<slug>/ledger.jsonl.
"""

import json
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


def guard(project, data, estimate_usd, approve_usd):
    """Raise BudgetError unless this spend is approved and within the cap."""
    cap = float(data.get("budget", {}).get("cap_usd", 0))
    already = spent(project)
    if approve_usd is None:
        raise BudgetError(
            f"Estimated cost is ${estimate_usd:.2f}. Ask the viewer, then re-run with "
            f"--approve-usd {estimate_usd:.2f} (or more) once they say yes."
        )
    if estimate_usd > float(approve_usd) + 1e-9:
        raise BudgetError(
            f"Estimate ${estimate_usd:.2f} is more than the approved ${float(approve_usd):.2f}. "
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
