"""Pathway state: a read-model derived from the append-only event list.
build() extracts event-derived facts; view() adds the time-derived fields for a given (virtual) now."""
import json

from engine.domain import STEPS, STEP_LABEL, parse_ts, days_between, step_name


def _j(v):
    try:
        return json.loads(v) if isinstance(v, str) and v[:1] in "{[" else v
    except Exception:
        return v


def build(meta, events):
    f = dict(meta)
    f["ts"] = {}          # step -> datetime (first event of that step)
    f["entered"] = {}
    f["contacts"], f["bookings"], f["messages"], f["slips"], f["loops"], f["handovers"], f["pulse"] = [], [], [], [], [], [], []
    f["coordinator"], f["stage"], f["g8"], f["flag"] = None, None, None, None
    f["coord_ts"] = None
    f["replies"] = []   # a nurse's approved written reply to a patient question
    f["calls_out"], f["t0_by"], f["questions"], f["first_contact_ts"], f["contact_ts"] = [], None, [], None, []
    for e in events:
        t, ts, val = e["type"], parse_ts(e["ts"]), _j(e["value"])
        if t in STEPS:
            f["ts"].setdefault(t, ts)
            if t == "T0":
                f["flag"] = val
                f["t0_by"] = e["entered_by"]
        elif t == "coordinator":
            f["coordinator"] = val
            if f["coord_ts"] is None:
                f["coord_ts"] = ts
        elif t == "handover":
            f["handovers"].append((ts, val))
            f["coordinator"] = val.get("to") if isinstance(val, dict) else f["coordinator"]
        elif t == "stage":
            f["stage"] = val
        elif t == "g8":
            try:
                f["g8"] = float(val)
            except Exception:
                pass
        elif t == "contact":
            f["contacts"].append((ts, val))
            if e["source"] == "coordinator-call":
                f["calls_out"].append(ts)
            if e["unit"] == "question":
                f["questions"].append((ts, val))
            if e["unit"] in ("phone", "eVisit"):
                f["contact_ts"].append(ts)
            if e["unit"] in ("phone", "eVisit") and (f["first_contact_ts"] is None or ts < f["first_contact_ts"]):
                f["first_contact_ts"] = ts   # earlier contact about the same complaint (process playbook: C1)
        elif t == "booking":
            f["bookings"].append((ts, val))
        elif t == "message":
            f["messages"].append((ts, val))
        elif t == "reply":
            f["replies"].append((ts, val))
        elif t == "slip":
            f["slips"].append((ts, val))
        elif t == "open_loop":
            f["loops"].append((ts, val))
        elif t.startswith("pulse:"):
            f["pulse"].append(dict(id=e["id"], ts=ts, item=t[6:], value=val, moment=e["unit"], by=e["entered_by"], confidence=e["confidence"]))
    done = [s for s in STEPS if s in f["ts"]]
    f["last_step"] = done[-1] if done else None
    f["last_ts"] = f["ts"][f["last_step"]] if done else None
    i = STEPS.index(f["last_step"]) + 1 if done else 0
    f["next_step"] = STEPS[i] if i < len(STEPS) else None
    f["done"] = "T6" in f["ts"]
    # latest booking for the target step after the last completed step
    f["booking"] = None
    for ts, b in reversed(f["bookings"]):
        if isinstance(b, dict) and f["last_ts"] and ts >= f["last_ts"] and b.get("step") in STEPS and STEPS.index(b["step"]) > STEPS.index(f["last_step"]):
            f["booking"] = dict(b, made=ts)
            break
    f["open_loop"] = None
    if f["loops"]:
        ts, v = f["loops"][-1]
        if isinstance(v, dict) and v.get("state") == "open":
            f["open_loop"] = dict(v, since=ts)
    f["slipped"] = bool(f["slips"]) and (not f["bookings"] or f["slips"][-1][0] > f["bookings"][-1][0])
    return f


def view(f, now):
    """Time-derived fields (days) for display and scoring."""
    v = dict(f)
    t0 = f["ts"].get("T0")
    v["days_total"] = days_between(t0, now) if t0 else 0.0
    v["days_in_step"] = days_between(f["last_ts"], now) if f["last_ts"] else 0.0
    v["step_label"] = step_name(f["cancer"], f["last_step"]) if f["last_step"] else "-"
    v["next_label"] = step_name(f["cancer"], f["next_step"]) if f["next_step"] else None
    t4, t2, t6 = f["ts"].get("T4"), f["ts"].get("T2"), f["ts"].get("T6")
    # the process playbook A2: C1 first contact = the earliest contact about the complaint (else T0). S0 and C1 are derived, never stored.
    c1 = min(f["first_contact_ts"], t0) if (f["first_contact_ts"] and t0) else t0
    t1 = f["ts"].get("T1")
    v["c1"] = c1
    v["c1_to_dx"] = days_between(c1, t4) if (c1 and t4) else None       # diagnostic interval: the headline
    v["c1_to_t1"] = days_between(c1, t1) if (c1 and t1) else None       # primary-care interval
    v["c1_to_t2"] = days_between(c1, t2) if (c1 and t2) else None
    v["t0_to_dx"] = days_between(t0, t4) if (t0 and t4) else None       # suspicion -> diagnosis (coordinator performance)
    v["t2_to_tx"] = days_between(t2, t6) if (t2 and t6) else None
    v["frail"] = f["g8"] is not None and f["g8"] <= 14
    return v
