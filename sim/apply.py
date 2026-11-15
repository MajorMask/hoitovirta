"""Shared mutations: create a pathway, apply a scheduled item, scan open loops. Used by the cohort builder,
the live simulator and the API, so all three produce identical events."""
import random

from engine import pulse, rules
from engine.domain import COORDINATORS, FLAG_CANCER, STEPS, add_days
from sim import model


def new_pathway_id(store):
    nums = [int(i[3:]) for i in store.meta if i.startswith("PW-") and i[3:].isdigit()]
    return f"PW-{(max(nums) if nums else 0) + 1:04d}"


DEMO_COORDINATOR = {"Länsi-Uusimaa": "Laura"}   # the persona the demo is run as


def pick_coordinator(store, county, human=False):
    """Least-loaded coordinator. Simulated arrivals never go to the demo persona; a human nurse's fast-track prefers her unless she is overloaded."""
    load = {c: 0 for c in COORDINATORS[county]}
    for pid in store.ids():
        f = store.facts(pid)
        if f["county"] == county and not f["done"] and f["coordinator"] in load:
            load[f["coordinator"]] += 1
    demo = DEMO_COORDINATOR.get(county)
    if demo:
        others = [c for c in load if c != demo]
        if not human:
            return min(others, key=lambda c: (load[c], c))
        avg = sum(load[c] for c in others) / max(len(others), 1)
        if load[demo] <= 2 * avg + 5:
            return demo
    return min(load, key=lambda c: (load[c], c))


def scan(store, pid, now=None):
    now = now or store.vnow
    for e in rules.scan(store.facts(pid), now):
        store.append(e["pathway_id"], "open_loop", e["ts"], e["value"], source=e["source"], confidence=1.0, entered_by="engine")


def create_pathway(store, pid, person, county, flag, t0, source, entered_by, coordinator=None, coordinator_at=None, contacts=()):
    """Create the pathway row and its first events (T0, g8, coordinator, earlier contacts)."""
    r = random.Random(f"{pid}:onset")
    cancer = FLAG_CANCER[flag]
    onset = int(model.ONSET[cancer] * r.lognormvariate(0, 0.5)) + (10 if person["language"] not in ("fi", "sv") else 0)
    store.add_pathway(dict(id=pid, name=person["name"], age=person["age"], sex=person["sex"], language=person["language"], county=county,
                           cancer=cancer, onset_days=onset, interpreter=bool(person["interpreter"])))
    for c in contacts:
        store.append(pid, "contact", add_days(t0, -c["days_ago"]), c["symptom"], unit=c["kind"], source="triage", entered_by="system")
    store.append(pid, "T0", t0, flag, unit="flag", source=source, entered_by=entered_by)
    if person.get("g8") is not None:
        store.append(pid, "g8", t0, str(person["g8"]), unit="score", source="assessment", entered_by="nurse")
    if coordinator:
        store.append(pid, "coordinator", coordinator_at or t0, coordinator, source="fast-track", entered_by=entered_by)


def apply_item(store, pid, item):
    """Apply one scheduled item (booking or pathway step) at its own timestamp."""
    kind, ts, payload = item
    f = store.facts(pid)
    if kind == "booking":
        store.append(pid, "booking", ts, payload, source="scheduling", entered_by=payload["by"])
    else:
        step = payload
        store.append(pid, step, ts, model.step_event_value(f["cancer"], step), source="ehr", entered_by="system")
        if step == "T2" and f["coordinator"] is None:  # baseline: a coordinator is named only when the referral arrives
            store.append(pid, "coordinator", ts, COORDINATORS[f["county"]][sum(map(ord, pid)) % 3], source="auto-assign", entered_by="system")
        if step == "T4":
            store.append(pid, "stage", ts, model.pick_stage(pid, f["cancer"], f["county"]), source="pathology", confidence=0.9, entered_by="system")
            pulse_after(store, pid, "diagnosis", ts)
        if step == "T6":
            pulse_after(store, pid, "treatment", ts)
    scan(store, pid, ts)


def roll_forward(store, pid, now):
    """Apply every scheduled item up to `now` (used to build the historical cohort)."""
    while True:
        items = model.plan_items(store.facts(pid))
        if not items or items[0][1] > now:
            break
        apply_item(store, pid, items[0])
    scan(store, pid, now)


def pulse_after(store, pid, moment, ts):
    """SYNTHETIC patient answers at a moment. Skipped for the human-driven demo pathways (nurse:Petra).
    In history, most alerts were already handled by a coordinator call (85%); alerts from the last few hours stay open."""
    f = store.facts(pid)
    if f["t0_by"] == "nurse:Petra":
        return
    answers = pulse.synth_answers(pid, moment, f)
    for item, value in answers.items():
        store.append(pid, f"pulse:{item}", ts, value, unit=moment, source="pulse:sms", entered_by="patient")
    if answers:
        call_ts = add_days(ts, 4 / 24)
        if call_ts <= store.vnow and pulse.alerts(store.facts(pid), ts) and random.Random(f"{pid}:{moment}:call").random() < 0.85:
            store.append(pid, "contact", call_ts, "Coordinator call", unit="call-out", source="coordinator-call", entered_by="coordinator:historic")
