"""Breach risk: an explainable logistic score, not a black box.
Target: the pathway misses the 6-week target (THL 21/2016: referral arrival -> first treatment, evidence id thl_6wk).
Weights are set by hand from the evidence and are to be calibrated on pilot data. The top 2 contributions are shown as reasons."""
import math

from app import ev
from engine.domain import DOMESTIC, LANGUAGES, STEPS, CANCER_LABEL

BUDGET = ev.v("thl_6wk")                  # 42 days
LIMITS = ev.get("step_limits")["limits"]  # target days to reach each step

B0 = -3.8
W = dict(budget=2.0, overdue=1.0, loop=1.6, slip=1.0, steps_left=1.0, language=0.5, frail=0.4, interpreter=0.2)
CANCER_W = {"lung": 0.45, "haematological": 0.6, "prostate": 0.25, "colorectal": 0.1, "breast": 0.0}


def score(v):
    """v is a state view. Returns (probability, [(contribution, reason text), ...] sorted desc)."""
    if v["done"]:
        return 0.0, []
    t2 = v["ts"].get("T2")
    # budget used: days since referral arrival if known, else half-weight days since first contact
    used = (v["days_total"] - ((v["ts"]["T2"] - v["ts"]["T0"]).total_seconds() / 86400.0)) if t2 else v["days_total"] * 0.5
    budget_used = max(used, 0.0) / BUDGET
    nxt = v["next_step"]
    limit = LIMITS.get(nxt, 7)
    overdue = max(v["days_in_step"] - limit, 0.0) / limit
    steps_left = (len(STEPS) - 1 - STEPS.index(v["last_step"])) / 6.0
    parts = [
        (W["budget"] * budget_used, f"{int(round(max(used, 0)))} of {BUDGET} days of the 6-week clock used, {len(STEPS) - 1 - STEPS.index(v['last_step'])} steps left"),
        (W["overdue"] * min(overdue, 3), f"{v['step_label']} done {int(v['days_in_step'])} days ago, next step due within {limit}"),
        (W["loop"] * (1 if v["open_loop"] else 0), f"Open loop: {v['open_loop']['reason']}" if v["open_loop"] else ""),
        (W["slip"] * (1 if v["slipped"] else 0), "Date slipped"),
        (W["steps_left"] * steps_left, f"{CANCER_LABEL[v['cancer']]}: many steps still ahead"),
        (W["language"] * (1 if v["language"] not in DOMESTIC else 0), f"Needs {LANGUAGES[v['language']]}: language barrier"),
        (W["frail"] * (1 if v.get("frail") else 0), "Frail (G8 14 or lower)"),
        (W["interpreter"] * (1 if v.get("interpreter") else 0), "Interpreter needed"),
        (CANCER_W[v["cancer"]], f"{CANCER_LABEL[v['cancer']]}: slower pathway on average"),
    ]
    z = B0 + sum(p for p, _ in parts)
    prob = 1 / (1 + math.exp(-z))
    reasons = sorted([(p, t) for p, t in parts if p > 0.05 and t], key=lambda x: -x[0])
    return prob, reasons
