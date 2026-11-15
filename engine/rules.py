"""Open-loop rules (safety net: no result without a next step). Rules, not AI. Thresholds come from data/evidence.json."""
import json

from app import ev
from engine.domain import DOMESTIC, FLAG_REASON, LOOP_REASON, fmt_ts, add_days

WINDOW = ev.v("loop_window")  # days a finished step may wait without a booked next step


def reason(f):
    step = f["last_step"]
    if step in ("T0", "T1", "T2"):
        return FLAG_REASON.get(f.get("flag")) or LOOP_REASON[(f["cancer"], "pre")]
    if step == "T3":
        return LOOP_REASON[(f["cancer"], "T3")]
    return LOOP_REASON[("any", step)]


def _event(pid, ts, state, why, rule):
    return dict(pathway_id=pid, ts=fmt_ts(ts), type="open_loop", value=json.dumps(dict(state=state, reason=why, rule=rule)),
                unit=None, source=f"engine:{rule}", confidence=1.0, entered_by="engine")


def scan(f, now):
    """Return open_loop events (open or closed) that this pathway state calls for. Pure: caller appends them."""
    out = []
    loop = f["open_loop"]
    if f["done"]:
        return [_event(f["id"], now, "closed", loop["reason"], "completed")] if loop else out
    if loop:
        b = f["booking"]
        if b and b["made"] >= loop["since"] and not f["slipped"]:
            out.append(_event(f["id"], max(b["made"], loop["since"]), "closed", loop["reason"], "booked"))
        return out
    if f["slipped"]:
        ts, _ = f["slips"][-1]
        out.append(_event(f["id"], ts, "open", "Date slipped", "slip"))
    elif f["next_step"] and not f["booking"] and f["last_ts"] is not None:
        due = add_days(f["last_ts"], WINDOW)
        if due <= now:
            out.append(_event(f["id"], due, "open", reason(f), "no_booking"))
    return out


def vulnerability(f):
    """0..1: who should be called first when risk is equal."""
    v = 0.0
    v += 0.35 if f["language"] not in DOMESTIC else 0.0
    v += 0.30 if f.get("frail") else 0.0
    v += 0.20 if f["age"] >= 75 else 0.0
    v += 0.15 if f.get("interpreter") else 0.0
    return min(v, 1.0)
