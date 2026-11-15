"""FHIR R4 Bundle adapter (stub, enough for a county pilot's weekly export). Mapping (also in store/schema.py):
  Patient                         -> pathway attributes (id pseudonymous; gender, birthDate, language, county in address.district)
  ServiceRequest category=suspicion -> T0 (authoredOn) ; category=referral -> T1 (authoredOn)
  Task (status accepted, focus=ServiceRequest) -> T2 (lastModified)
  Procedure category=diagnostic   -> T3 (performedDateTime) ; category=treatment -> T6
  Condition (recordedDate)        -> T4 ; Condition.stage.summary.text -> stage
  Encounter type=MDT              -> T5 (period.start)
  Observation code=G8             -> g8 (valueInteger)
Anything else in the bundle is ignored, never guessed."""
from datetime import date

CATEGORY_STEP = {("ServiceRequest", "suspicion"): "T0", ("ServiceRequest", "referral"): "T1", ("Procedure", "diagnostic"): "T3", ("Procedure", "treatment"): "T6"}


def _cat(res):
    for c in res.get("category", []) if isinstance(res.get("category"), list) else [res.get("category") or {}]:
        for cd in (c or {}).get("coding", []):
            if cd.get("code"):
                return cd["code"]
    return None


def _pid(res):
    ref = (res.get("subject") or res.get("patient") or res.get("for") or {}).get("reference", "")
    return ref.split("/")[-1] if ref else None


def rows_from_bundle(bundle):
    if bundle.get("resourceType") != "Bundle":
        raise ValueError("expected a FHIR Bundle")
    res = [e["resource"] for e in bundle.get("entry", []) if "resource" in e]
    patients = {}
    for r in res:
        if r.get("resourceType") == "Patient":
            ext = {e.get("url"): e for e in r.get("extension", [])}
            patients[r["id"]] = dict(
                patient_name=(r.get("name") or [{}])[0].get("text") or "Unknown", sex=("f" if r.get("gender") == "female" else "m"),
                age=(date.today().year - int(r["birthDate"][:4])) if r.get("birthDate") else 60,
                language=((r.get("communication") or [{}])[0].get("language", {}).get("coding") or [{}])[0].get("code", "fi"),
                county=((r.get("address") or [{}])[0].get("district")), cancer=(ext.get("cancer-pathway") or {}).get("valueString"))
    rows = []
    for r in res:
        t, base = r.get("resourceType"), {}
        pid = _pid(r)
        if not pid:
            continue
        base = dict(pathway_id=pid, **{k: patients.get(pid, {}).get(k) for k in ("patient_name", "age", "sex", "language", "county", "cancer")})
        if (t, _cat(r)) in CATEGORY_STEP:
            ts = r.get("authoredOn") or r.get("performedDateTime") or (r.get("performedPeriod") or {}).get("start")
            rows.append(dict(base, type=CATEGORY_STEP[(t, _cat(r))], ts=ts, value=(r.get("code") or {}).get("text")))
        elif t == "Task" and r.get("status") == "accepted":
            rows.append(dict(base, type="T2", ts=r.get("lastModified"), value="Referral received"))
        elif t == "Condition":
            rows.append(dict(base, type="T4", ts=r.get("recordedDate"), value=(r.get("code") or {}).get("text")))
            st = ((r.get("stage") or [{}])[0].get("summary") or {}).get("text")
            if st:
                rows.append(dict(base, type="stage", ts=r.get("recordedDate"), value=st))
        elif t == "Encounter" and any(c.get("code") == "MDT" for tp in r.get("type", []) for c in tp.get("coding", [])):
            rows.append(dict(base, type="T5", ts=(r.get("period") or {}).get("start"), value="MDT"))
        elif t == "Observation" and any(c.get("code") == "G8" for c in (r.get("code") or {}).get("coding", [])):
            rows.append(dict(base, type="g8", ts=r.get("effectiveDateTime"), value=str(r.get("valueInteger"))))
    return [x for x in rows if x.get("ts")]
