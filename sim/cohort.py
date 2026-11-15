"""Synthetic cohort: Länsi-Uusimaa in detail (~300 pathways) plus four lighter counties, 5 cancers, 6 languages.
ALL SYNTHETIC. Five named demo pathways wait in Laura's worklist so the demo starts with real work to do."""
import random
from datetime import timedelta

from engine.domain import COORDINATORS, RED_FLAGS, add_days
from sim import apply as ap
from sim.people import FLAG_W, person, pick

COUNTY_N = {"Länsi-Uusimaa": 300, "Helsinki": 90, "Vantaa–Kerava": 70, "Pirkanmaa": 70, "Lappi": 50}
PILOT_DAYS = 60            # pathways younger than this had a coordinator named at first contact (the pilot)
COORD_WEIGHTS = {"Länsi-Uusimaa": [0.2, 0.4, 0.4]}


def _flag(r, cancer):
    return r.choices(RED_FLAGS[cancer], weights=[FLAG_W[x] for x in RED_FLAGS[cancer]])[0]


def generate(store, now, seed=7):
    r = random.Random(seed)
    store.vnow = now
    for county, n in COUNTY_N.items():
        w = COORD_WEIGHTS.get(county, [1 / 3] * 3)
        for _ in range(n):
            pid = ap.new_pathway_id(store)
            p = person(r, county)
            age_days = r.uniform(1, 160)
            t0 = add_days(now, -age_days)
            flag = _flag(r, p["cancer"])
            coord = r.choices(COORDINATORS[county], weights=w)[0]
            pilot = age_days < PILOT_DAYS
            prior = [dict(days_ago=r.randint(8, 25), kind="phone", symptom="same symptom") for _ in range(2)] if (flag.startswith("Back or bone")) else []
            if not prior and r.random() < 0.35:   # an earlier contact about the same complaint: C1 is before T0 (process playbook)
                prior = [dict(days_ago=r.randint(4, 28), kind=r.choice(["phone", "eVisit"]), symptom="same symptom") for _ in range(r.choice([1, 1, 2]))]
            ap.create_pathway(store, pid, p, county, flag, t0, source="ehr-import", entered_by="system",
                              coordinator=coord if pilot else None, contacts=prior)
            store.facts(pid)
            ap.pulse_after(store, pid, "suspicion", t0)
            ap.roll_forward(store, pid, now)
    _anchors(store, now)
    seed_demo_pulse(store, now)
    return len(store.meta)


def seed_demo_pulse(store, now):
    """Deterministic synthetic answers keep demo KPI tiles visible after every reset."""
    for county in ("Länsi-Uusimaa", "Helsinki", "Vantaa–Kerava"):
        pids = [pid for pid in sorted(store.ids()) if store.meta[pid]["county"] == county][:10]
        for i, pid in enumerate(pids):
            # PU5 is only valid after a yes to PU5a. The 8/10 yes share is synthetic demo data.
            answers = {"PU4": "yes", "PU5a": "yes", "PU5": "yes" if i < 8 else "no",
                       "PU7": str(3 + (i % 2)), "PU9": str((7, 8, 9, 10, 6)[i % 5])}
            for item, value in answers.items():
                store.append(pid, f"pulse:{item}", now, value, unit="handover", source="pulse:demo-seed", entered_by="patient")
            if county == "Länsi-Uusimaa" and i < 3:
                comments = ("Clear explanations helped.", "Waiting for the next appointment affected me.", "I felt listened to.")
                store.append(pid, "pulse:PU9b", now, comments[i], unit="handover", source="pulse:demo-seed", entered_by="patient")


def _anchors(store, now):
    """Five demo pathways for coordinator Laura (Länsi-Uusimaa): each waits for her."""
    d = lambda n: add_days(now, -n)
    specs = [
        ("PW-D1", dict(name="Amina H.", age=67, sex="f", language="ar", interpreter=True, g8=15), "Positive FIT", 12, [], []),
        ("PW-D2", dict(name="Matti K.", age=64, sex="m", language="fi", interpreter=False, g8=None), "Back or bone pain, 3rd visit", 9,
         [dict(days_ago=30, kind="phone", symptom="back pain"), dict(days_ago=18, kind="eVisit", symptom="back pain")], []),
        ("PW-D3", dict(name="Juha L.", age=58, sex="m", language="fi", interpreter=False, g8=None), "Nodule on X-ray or CT", 10, [], []),
        ("PW-D4", dict(name="Pekka V.", age=69, sex="m", language="sv", interpreter=False, g8=13), "Raised PSA", 25, [], ["T1", "T2", "T3"]),
        ("PW-D5", dict(name="Sara N.", age=52, sex="f", language="en", interpreter=False, g8=None), "Abnormal mammogram", 20, [], ["T1", "T2", "slip"]),
    ]
    for pid, person_, flag, days, contacts, steps in specs:
        t0 = d(days)
        ap.create_pathway(store, pid, person_, "Länsi-Uusimaa", flag, t0, source="triage", entered_by="nurse:Petra",
                          coordinator="Laura", contacts=contacts)
        offsets = {"T1": 0.10, "T2": 0.20, "T3": 0.60}   # fraction of elapsed time at which earlier steps happened
        for st_ in steps:
            if st_ == "slip":
                store.append(pid, "booking", d(3), dict(step="T3", due=_iso(add_days(now, 2).replace(hour=13, minute=0, second=0, microsecond=0)), by="system"), source="scheduling", entered_by="system")
                store.append(pid, "slip", d(1), dict(step="T3", why="Hospital moved the appointment"), source="patient", entered_by="patient")
            else:
                store.append(pid, st_, add_days(t0, days * offsets[st_]), None, source="ehr", entered_by="system")
        ap.scan(store, pid, now)


def _iso(dt):
    from engine.domain import fmt_ts
    return fmt_ts(dt)
