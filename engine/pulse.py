"""Hoitovirta Pulse (docs/PULSE-INSTRUMENT.md): at most 2 questions per moment, same item codes everywhere.
Objective answers only. AI converts speech to a field; the patient confirms. A human acts on signals (worry >= 4 -> a call)."""
import random

from app import ev
from engine.domain import DOMESTIC, days_between

DISTRESS_CUTOFF = ev.v("distress_cutoff")  # NCCN Distress Thermometer, 4 or more
ALERT_WINDOW_DAYS = 7
MOMENT_WINDOW_DAYS = 7

# item -> (answer kind, option keys). Option labels are translated in app/i18n.py as "opt_<item>_<key>".
NUM = [str(i) for i in range(11)]
CODEBOOK = {
    "PU1": ("choice", ["week", "w2_4", "m1_3", "m3p"]),         # when did you first notice it -> patient interval (days)
    "PU2": ("choice", ["1", "2", "3p"]),                        # contacts before referral
    "PU3": ("choice", ["time", "cost", "language", "fear", "noappt", "notserious"]),
    "PU4": ("choice", ["yes", "unsure", "no"]),                 # do you know what happens next
    "PU5a": ("choice", ["yes", "no", "not_tried"]),            # asked first; not_tried is an explicit third response
    "PU5": ("choice", ["yes", "no"]),                           # conditional on PU5a=yes
    "PU6": ("choice", ["yes", "partly", "no"]),                 # understood in your language
    "PU7": ("scale", NUM),                                      # worry this week 0-10
    "PU8": ("choice", ["0", "1", "2", "3p"]),                   # times you repeated your story
    "PU9": ("scale", NUM),                                      # likelihood to recommend 0-10
    "PU9b": ("text", ["skip"]),                                 # optional patient comment; voice is transcribed, then confirmed
}
PU1_DAYS = {"week": 4, "w2_4": 21, "m1_3": 60, "m3p": 120}     # midpoint days stored with the option

# moment -> (items, window in days from the trigger)
MOMENTS = {
    "handover": ["PU4", "PU5a"],
    "diagnosis": ["PU9", "PU7", "PU9b"],
    "treatment": ["PU9", "PU8", "PU9b"],
    "suspicion": ["PU4", "PU7"],
    "first_contact": ["PU1", "PU2"],
}
CONDITIONAL = {"handover": {"PU5a": {"yes": "PU5"}}}
OPTIONAL = {"diagnosis": ["PU9b"], "treatment": ["PU9b"]}
PRIORITY = ["handover", "treatment", "diagnosis", "first_contact", "suspicion"]  # latest, most relevant first


def valid(item, value):
    if item not in CODEBOOK:
        return False
    kind, opts = CODEBOOK[item]
    if kind == "text":
        value = str(value).strip()
        return value == "skip" or bool(value) and len(value) <= 500
    return str(value) in opts


def _triggers(f):
    """moment key -> trigger datetime, from the pathway's events."""
    t = {}
    if "T0" in f["ts"]:
        t["first_contact"] = f["ts"]["T0"]
        t["suspicion"] = f["ts"]["T0"]
    if "T4" in f["ts"]:
        t["diagnosis"] = f["ts"]["T4"]
    if "T6" in f["ts"]:
        t["treatment"] = f["ts"]["T6"]
    return t


def pending(f, now):
    """The next moment due for this patient: {'moment': key, 'items': [...]} or None. At most 2 items."""
    answered = {r["moment"] for r in f["pulse"] if r["moment"]}
    trig = _triggers(f)
    cands = []
    for ts, m in f["messages"]:   # each approved message is a handover moment
        cands.append((ts, "handover", f"handover:{ts.isoformat()}"))
    for ts, h in f["handovers"]:
        cands.append((ts, "handover", f"handover:{ts.isoformat()}"))
    for k, ts in trig.items():
        cands.append((ts, k, k))
    due = [(ts, m, key) for ts, m, key in cands if key not in answered and days_between(ts, now) <= MOMENT_WINDOW_DAYS]
    if not due:
        return None
    due.sort(key=lambda x: (PRIORITY.index(x[1]), -x[0].timestamp()))
    ts, m, key = due[0]
    items = list(MOMENTS[m])
    if m == "first_contact" and f["language"] not in DOMESTIC:
        items = ["PU1", "PU6"]  # keep to 2 questions: PU2 is cross-checked with the system, PU6 asks about language
    return dict(moment=key, kind=m, items=items, conditional=CONDITIONAL.get(m, {}), optional=OPTIONAL.get(m, []))


def latest(f, item):
    rs = [r for r in f["pulse"] if r["item"] == item]
    return rs[-1] if rs else None


def alerts(f, now):
    """Active Pulse signals a person must act on (cleared by a coordinator call after the answer)."""
    out = []
    answered = list(f["calls_out"]) + [t for t, _ in f.get("replies", [])]   # a call or an approved written reply clears the signals
    last_call = max(answered) if answered else None

    def active(r):
        return r and days_between(r["ts"], now) <= ALERT_WINDOW_DAYS and not (last_call and last_call >= r["ts"])

    r = latest(f, "PU7")
    if active(r) and float(r["value"]) >= DISTRESS_CUTOFF:
        out.append(dict(item="PU7", priority=3, text=f"Worry {int(float(r['value']))} of 10: call today or the next working day"))
    r = latest(f, "PU5")
    if active(r) and r["value"] == "no":
        out.append(dict(item="PU5", priority=2, text="Could not reach the nurse within 1 working day: call"))
    r = latest(f, "PU4")
    if active(r) and r["value"] in ("no", "unsure"):
        out.append(dict(item="PU4", priority=1, text="Does not know what happens next: call"))
    if f["questions"]:
        ts, text = f["questions"][-1]
        if days_between(ts, now) <= ALERT_WINDOW_DAYS and not (last_call and last_call >= ts):
            out.append(dict(item="Q", priority=2, text="Patient question: call"))
    out.sort(key=lambda a: -a["priority"])
    return out


# ---- synthetic patient answers (the cohort and the live simulator) -----------------------------------------------------
def synth_answers(pid, moment, f):
    """Deterministic synthetic answers for a moment (SYNTHETIC; invented distributions, not findings)."""
    r = random.Random(f"{pid}:pulse:{moment}")
    if r.random() > 0.6:
        return {}                     # not everyone answers
    barrier = (0.6 if f["language"] not in DOMESTIC else 0.0) + (0.4 if f.get("frail") else 0.0) + (0.5 if f["open_loop"] else 0.0)
    out = {}
    for item in MOMENTS[moment if moment in MOMENTS else "handover"]:
        if item == "PU4":
            p_yes = max(0.25, 0.68 - 0.18 * barrier)
            x = r.random()
            out[item] = "yes" if x < p_yes else ("unsure" if x < p_yes + 0.55 * (1 - p_yes) else "no")
        elif item == "PU7":
            out[item] = str(max(0, min(10, round(r.gauss(3.0 + 1.2 * barrier, 2.2)))))
        elif item == "PU9":
            out[item] = str(max(0, min(10, round(r.gauss(7.4 - 0.9 * barrier, 1.8)))))
        elif item == "PU5":
            out[item] = "yes" if r.random() < 0.82 - 0.1 * barrier else "no"
        elif item == "PU8":
            out[item] = r.choices(["0", "1", "2", "3p"], weights=[30, 35, 20, 15])[0]
    return out
