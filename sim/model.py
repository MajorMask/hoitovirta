"""Synthetic pathway model. SYNTHETIC: parameters are invented to look plausible, calibrated only so the lung
medians sit near the public Yle MOT figures (primary ~41 d, specialist ~58 d). Nothing here is a finding.
Deterministic: the same pathway always plans the same durations (rng seeded by pathway id + step), so the
future can be rebuilt from events after a restart."""
import json
import math
import random

from engine.domain import DOMESTIC, STEPS, add_days, fmt_ts, parse_ts

# Median days INTO each step, by cancer (T1 = first contact to referral sent, etc.)
MEDIANS = {
    "lung": {"T1": 36, "T2": 3, "T3": 14, "T4": 13, "T5": 9, "T6": 20},
    "breast": {"T1": 10, "T2": 3, "T3": 7, "T4": 6, "T5": 5, "T6": 12},
    "colorectal": {"T1": 12, "T2": 3, "T3": 11, "T4": 6, "T5": 6, "T6": 14},
    "prostate": {"T1": 20, "T2": 4, "T3": 10, "T4": 10, "T5": 6, "T6": 18},
    "haematological": {"T1": 30, "T2": 4, "T3": 8, "T4": 12, "T5": 5, "T6": 10},
}
ONSET = {"lung": 56, "breast": 25, "colorectal": 30, "prostate": 40, "haematological": 45}  # patient interval, days
COUNTY_SPEED = {"Länsi-Uusimaa": 1.05, "Helsinki": 1.08, "Vantaa–Kerava": 1.12, "Pirkanmaa": 0.9, "Lappi": 1.2}
LANG_EXTRA_T1 = 9      # extra days in primary care for patients without a domestic language (synthetic equity gap)
STAGE_UNKNOWN = {"Pirkanmaa": 0.28}
DEFAULT_UNKNOWN = 0.58
STAGE_ORDER = ["I", "II", "III", "IV"]
STAGE_W = {"lung": [0.14, 0.12, 0.28, 0.46], "breast": [0.42, 0.30, 0.18, 0.10], "colorectal": [0.22, 0.26, 0.31, 0.21],
           "prostate": [0.30, 0.42, 0.18, 0.10], "haematological": [0.05, 0.15, 0.30, 0.50]}

ANCHORS_STALLED = {"PW-D1", "PW-D2", "PW-D3", "PW-D4", "PW-D5"}  # demo pathways that wait for the coordinator


def rng(pid, step, salt=""):
    return random.Random(f"{pid}:{step}:{salt}")


def coordinated(f):
    """Coordinator named at (or within a day of) first contact: the pilot scenario."""
    return f["coord_ts"] is not None and f["ts"].get("T0") is not None and (f["coord_ts"] - f["ts"]["T0"]).total_seconds() <= 86400


def duration(f, step):
    r = rng(f["id"], step, "dur")
    base = MEDIANS[f["cancer"]][step]
    if step == "T1" and f["language"] not in DOMESTIC:
        base += LANG_EXTRA_T1
    mult = COUNTY_SPEED[f["county"]]
    if step in ("T3", "T4", "T5", "T6") and f.get("g8") is not None and f["g8"] <= 14:
        mult *= 1.2
    if coordinated(f):
        mult *= {"T1": 0.6, "T2": 0.7}.get(step, 0.9)
    return max(base * mult * r.lognormvariate(0, 0.45), 0.5)


def stalls(f, step):
    if f["id"] in ANCHORS_STALLED:
        return True
    r = rng(f["id"], step, "stall")
    p = 0.10 if (f["cancer"] == "haematological" and step == "T3") else (0.05 if step == "T3" else 0.02)
    if f["language"] not in DOMESTIC:
        p *= 1.5
    if f.get("g8") is not None and f["g8"] <= 14:
        p *= 1.3
    return r.random() < p


def plan_items(f):
    """Remaining scheduled items for a pathway, in time order: ('booking', ts, payload) and ('step', ts, step)."""
    step, last = f["next_step"], f["last_ts"]
    if step is None or last is None:
        return []
    if f["booking"]:
        return [("step", parse_ts(f["booking"]["due"]), step)]
    if f["id"] in ANCHORS_STALLED:
        return []          # the named demo patients wait for the coordinator: nobody else resolves them
    r = rng(f["id"], step, "plan")
    dur = duration(f, step)
    if stalls(f, step) or f["slipped"]:
        chase = r.uniform(25, 45)  # the patient eventually chases; until then nobody has booked anything
        b_ts = add_days(last, chase)
        due = add_days(b_ts, dur)
        by = "patient-chase"
    else:
        b_ts = add_days(last, min(r.uniform(0.3, 3.0), dur * 0.6))
        due = add_days(last, dur)
        by = "system"
    return [("booking", b_ts, dict(step=step, due=fmt_ts(due), by=by)), ("step", due, step)]


def pick_stage(pid, cancer, county):
    r = rng(pid, "T4", "stage")
    if r.random() < STAGE_UNKNOWN.get(county, DEFAULT_UNKNOWN):
        return "unknown"
    return r.choices(STAGE_ORDER, weights=STAGE_W[cancer])[0]


def step_event_value(cancer, step):
    from engine.domain import step_name
    return step_name(cancer, step)
