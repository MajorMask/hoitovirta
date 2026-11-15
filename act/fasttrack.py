"""Fast-track: a red-flag tap starts the clock (T0) and names a coordinator. The only writer of new pathways."""
import time

from engine.domain import FLAG_CANCER
from sim import apply as ap


def start(store, sim, call, flag, nurse, take=True, extra=()):
    """call: an incoming call dict (see sim.people.make_call). Returns the new pathway summary."""
    if flag not in FLAG_CANCER:
        raise ValueError("unknown red flag")
    with store.lock:
        pid = ap.new_pathway_id(store)
        county = call["county"]
        human = nurse != "sim"
        coordinator = ap.pick_coordinator(store, county, human=human)
        t0 = store.vnow
        person = dict(name=call["name"], age=call["age"], sex=call["sex"], language=call["language"],
                      interpreter=call["interpreter"], g8=call.get("g8"))
        ap.create_pathway(store, pid, person, county, flag, t0, source="triage", entered_by=f"nurse:{nurse}",
                          coordinator=coordinator, contacts=call.get("prior", []))
        for ef in dict.fromkeys(x for x in extra if x in FLAG_CANCER and x != flag):   # every other ticked flag is recorded with the pathway
            store.append(pid, "red_flag", t0, ef, unit="extra", source="triage", entered_by=f"nurse:{nurse}")
        ap.scan(store, pid, t0)
        if human:
            store.human_new[pid] = time.time()   # pinned on the coordinator's list for a while
        sim.schedule(pid)
        return dict(pathway_id=pid, coordinator=coordinator, county=county, cancer=FLAG_CANCER[flag], t0=t0.isoformat())


def start_suggested(store, sim, pathway_id, flag, nurse, extra=()):
    """Clinician acceptance of a voice suggestion on an existing pathway; the tap is the only T0 writer here."""
    if flag not in FLAG_CANCER:
        raise ValueError("unknown red flag")
    with store.lock:
        if pathway_id not in store.meta:
            raise KeyError(pathway_id)
        f = store.facts(pathway_id)
        if f["ts"].get("T0"):
            raise ValueError("this pathway already has T0")
        if FLAG_CANCER[flag] != store.meta[pathway_id]["cancer"]:
            raise ValueError("red flag does not match pathway cancer")
        if not any(e["type"] == "suspicion_suggested" for e in store.events_for(pathway_id)):
            raise ValueError("no caller suggestion for this pathway")
        county = store.meta[pathway_id]["county"]
        coordinator = ap.pick_coordinator(store, county, human=True)
        ts = store.vnow
        store.append(pathway_id, "T0", ts, flag, unit="flag", source="triage", entered_by=f"nurse:{nurse}")
        store.append(pathway_id, "coordinator", ts, coordinator, source="fast-track", entered_by=f"nurse:{nurse}")
        for ef in dict.fromkeys(x for x in extra if x in FLAG_CANCER and x != flag):
            store.append(pathway_id, "red_flag", ts, ef, unit="extra", source="triage", entered_by=f"nurse:{nurse}")
        store.human_new[pathway_id] = time.time()
        ap.scan(store, pathway_id, ts)
        sim.schedule(pathway_id)
        return dict(pathway_id=pathway_id, coordinator=coordinator, county=county, cancer=FLAG_CANCER[flag], t0=ts.isoformat())
