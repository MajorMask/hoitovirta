"""Synthetic screening invitations (breast and colorectal) and how outreach converts. ALL SYNTHETIC.
The invented response rates are shaped like the public picture (about 80% for breast, lower for people without a domestic language)
but they are not findings; real rates come from the Cancer Registry (see data/evidence.json)."""
import random

from engine.domain import COUNTIES, DOMESTIC, add_days
from sim.people import LANG_MIX, NAMES, pick

PROGRAMMES = {"breast": "Breast screening", "colorectal": "Bowel screening (FIT)"}
N_INVITES = {"Länsi-Uusimaa": 520, "Helsinki": 160, "Vantaa–Kerava": 130, "Pirkanmaa": 130, "Lappi": 90}   # per programme
BASE = {"breast": 0.80, "colorectal": 0.72}
COUNTY_F = {"Länsi-Uusimaa": 0.97, "Helsinki": 0.94, "Vantaa–Kerava": 0.95, "Pirkanmaa": 1.04, "Lappi": 1.02}
LANG_F = 0.78                      # relative response for people without a domestic language (synthetic)
AGE = {"breast": (50, 69), "colorectal": (60, 72)}
BARRIERS = ["time", "cost", "language", "fear", "noappt", "notserious"]
BARRIER_W_DOMESTIC = [30, 10, 2, 20, 20, 18]
BARRIER_W_OTHER = [15, 10, 35, 12, 13, 15]


def barrier_for(r, language):
    return r.choices(BARRIERS, weights=BARRIER_W_DOMESTIC if language in DOMESTIC else BARRIER_W_OTHER)[0]


def generate(scr, now, seed=11):
    r = random.Random(seed)
    n = 0
    for county in COUNTIES:
        for prog in PROGRAMMES:
            for _ in range(N_INVITES[county]):
                lang = pick(r, LANG_MIX[county])
                sex = "f" if prog == "breast" else r.choice("fm")
                first = r.choice(NAMES[lang][0 if sex == "f" else 1])
                lo, hi = AGE[prog]
                days_ago = r.uniform(3, 150)
                inv_id = f"S-{n + 1:05d}"
                inv = dict(id=inv_id, county=county, programme=prog, name=f"{first} {r.choice('ABEHJKLMNPRSTVW')}.", age=r.randint(lo, hi),
                           language=lang, invited_ts=add_days(now, -days_ago).strftime("%Y-%m-%dT%H:%M:%SZ"))
                scr.add_invite(inv)
                n += 1
                p = BASE[prog] * COUNTY_F[county] * (1.0 if lang in DOMESTIC else LANG_F)
                if r.random() < p:
                    when = min(days_ago - 0.1, r.expovariate(1 / 9.0))
                    scr.append(inv_id, "screened", add_days(now, -days_ago + when), prog, "system")
                elif days_ago > 28 and r.random() < 0.3:   # some non-responders replied to a check with their barrier (Pulse PU3)
                    scr.append(inv_id, "barrier", add_days(now, -days_ago + 30), barrier_for(r, lang), "patient")
    return n
