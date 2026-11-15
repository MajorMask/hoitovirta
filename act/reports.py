"""Reports (diagnostics): structure a report, write the factual events, queue doubtful ones for a human, flag loops.
Automatic (confidence >= 0.7 and model/rules agree): the report event, 'first test done' (T3), and the safety-net flag.
Always human: stage and diagnosis (T4) are written only after a person confirms them."""
import json
import uuid

from engine.domain import STEPS, step_name
from sim import apply as ap
from structure import report as sr

SAMPLES = [
    dict(label="CT chest: nodule, no next step", text="CT thorax with contrast: 14 mm spiculated nodule in the right upper lobe, suspicious for malignancy. No pleural effusion. No comparison available."),
    dict(label="CT chest: next step stated", text="CT thorax: 12 mm spiculated nodule right upper lobe, suspicious for malignancy. Recommend PET-CT and referral to the lung MDT."),
    dict(label="Pathology: carcinoma", text="Core biopsy, right breast: invasive ductal carcinoma, grade 2. Stage cannot be assigned from this specimen. MDT review recommended."),
    dict(label="Lab: myeloma screen", text="Serum protein electrophoresis: small M-spike 8 g/L. Serum free light chains: kappa 85 mg/L, kappa/lambda ratio 6.2 (raised)."),
    dict(label="Unclear report (needs a check)", text="Scan done, see clinic notes. Follow up as agreed."),
]


def _fields(s):
    return {k: s.get(k) for k in ("kind", "test", "finding", "suspicious", "next_step_stated", "next_step", "stage")}


def _report_event(store, pid, rid, status, fields, conf, text, engine, by, agree=None):
    return store.append(pid, "report", store.vnow, dict(report_id=rid, status=status, fields=fields, agreement=agree, engine=engine, excerpt=text[:500]),
                        unit=fields.get("kind"), source=f"report:{engine}", confidence=conf, entered_by=by)


def _ensure_first_test(store, pid, fields, conf, by, rid, saved):
    f = store.facts(pid)
    if fields["kind"] in ("imaging", "lab") and "T3" not in f["ts"]:
        for s in ("T1", "T2"):
            if s not in f["ts"]:
                store.append(pid, s, store.vnow, step_name(f["cancer"], s), source=f"report:{rid}:inferred", confidence=conf, entered_by=by)
        store.append(pid, "T3", store.vnow, fields.get("test") or step_name(f["cancer"], "T3"), source=f"report:{rid}", confidence=conf, entered_by=by)
        saved.append("First test marked done: " + (fields.get("test") or "test"))
        loop = store.facts(pid)["open_loop"]
        if loop and loop.get("rule") in ("no_booking", "slip"):   # the missing test has now happened: that loop is resolved
            store.append(pid, "open_loop", store.vnow, json.dumps(dict(state="closed", reason=loop["reason"], rule="test-done")),
                         source="engine:report", confidence=1.0, entered_by="engine")
            saved.append("Closed the open loop: " + loop["reason"])


def _flag_loop(store, pid, fields, rid, saved):
    f = store.facts(pid)
    if fields["suspicious"] and not fields["next_step_stated"] and not f["open_loop"] and not f["done"]:
        store.append(pid, "open_loop", store.vnow, json.dumps(dict(state="open", reason="Suspicious finding in a report, no next step stated", rule="report", report_id=rid)),
                     source="engine:report", confidence=1.0, entered_by="engine")
        saved.append("Flagged as an open loop: the coordinator sees it in Today")


def _apply_auto(store, sim, pid, fields, conf, by, rid):
    saved = []
    _ensure_first_test(store, pid, fields, conf, by, rid, saved)
    _flag_loop(store, pid, fields, rid, saved)
    ap.scan(store, pid, store.vnow)
    sim.schedule(pid)
    return saved


def ingest(store, sim, pid, text, by):
    s = sr.structure(text)
    rid = uuid.uuid4().hex[:8]
    fields = _fields(s)
    status = "needs_check" if s["needs_check"] else "saved"
    with store.lock:
        _report_event(store, pid, rid, status, fields, s["confidence"], text, s["engine"], by, s["agreement"])
        saved = _apply_auto(store, sim, pid, fields, s["confidence"], by, rid) if status == "saved" else []
        f = store.facts(pid)
        propose = dict(diagnosis=bool(fields["kind"] == "pathology" and fields["suspicious"] and "T4" not in f["ts"]),
                       stage=fields["stage"] if fields["stage"] != "unknown" else None)
    return dict(report_id=rid, pathway_id=pid, status=status, fields=fields, confidence=s["confidence"], agreement=s["agreement"],
                engine=s["engine"], saved=saved, propose=propose)


def _latest(store):
    """report_id -> latest report event (value parsed)."""
    out = {}
    with store.lock:
        for e in store.log:
            if e["type"] == "report":
                v = json.loads(e["value"])
                out[v["report_id"]] = dict(event=e, v=v)
    return out


def confirm(store, sim, rid, fields, include, by):
    cur = _latest(store).get(rid)
    if not cur:
        raise KeyError("unknown report")
    e, v = cur["event"], cur["v"]
    pid = e["pathway_id"]
    fields = {**v["fields"], **{k: fields[k] for k in fields if k in v["fields"]}}
    saved = []
    with store.lock:
        _report_event(store, pid, rid, "confirmed", fields, 1.0, v["excerpt"], "human-checked", by, v.get("agreement"))
        f = store.facts(pid)
        saved += _apply_auto_checked(store, sim, pid, fields, by, rid)
        f = store.facts(pid)
        if "stage" in include and fields.get("stage") in ("I", "II", "III", "IV"):
            store.append(pid, "stage", store.vnow, fields["stage"], source=f"report:{rid}", confidence=1.0, entered_by=by)
            saved.append(f"Stage {fields['stage']} recorded")
        if "T4" in include and "T4" not in f["ts"] and fields["kind"] == "pathology" and fields["suspicious"]:
            for s_ in ("T1", "T2", "T3"):
                if s_ not in f["ts"]:
                    store.append(pid, s_, store.vnow, step_name(f["cancer"], s_), source=f"report:{rid}:inferred", confidence=1.0, entered_by=by)
            store.append(pid, "T4", store.vnow, "Diagnosis (confirmed by a person)", source=f"report:{rid}", confidence=1.0, entered_by=by)
            saved.append("Diagnosis recorded (confirmed by a person)")
        ap.scan(store, pid, store.vnow)
        sim.schedule(pid)
    return dict(report_id=rid, status="confirmed", saved=saved)


def _apply_auto_checked(store, sim, pid, fields, by, rid):
    saved = []
    _ensure_first_test(store, pid, fields, 1.0, by, rid, saved)
    _flag_loop(store, pid, fields, rid, saved)
    return saved


def listing(store, county=None, limit=15):
    """Queue (needs check) and recent reports, newest first. Staff view: shows patient names."""
    items = []
    for rid, cur in _latest(store).items():
        e, v = cur["event"], cur["v"]
        m = store.meta[e["pathway_id"]]
        if county and m["county"] != county:
            continue
        items.append(dict(report_id=rid, pathway_id=e["pathway_id"], name=m["name"], coordinator=store.facts(e["pathway_id"])["coordinator"], county=m["county"], cancer=m["cancer"], status=v["status"],
                          fields=v["fields"], confidence=e["confidence"], engine=v["engine"], excerpt=v["excerpt"], ts=e["ts"], event_id=e["id"],
                          flag=bool(v["fields"]["suspicious"] and not v["fields"]["next_step_stated"])))
    items.sort(key=lambda x: -x["event_id"])
    return dict(queue=[i for i in items if i["status"] == "needs_check"], recent=items[:limit],
                flagged=[i for i in items if i["flag"] and i["status"] != "needs_check"][:limit])
