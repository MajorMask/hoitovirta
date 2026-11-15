"""Ingest adapters turn outside data into events. Everything goes through ONE validated path (ingest_events), the same event schema
the simulator and the screens write. Adapters: EHR export CSV (ehr_csv), FHIR Bundle (fhir). SYNTHETIC samples only in this repo.

Why adapters are thin: a county's EHR export differs (LUVN, Apotti, Lifecare, Pegasos, Omni360), so the adapter's job is only to map
columns or resources to (pathway_id, type, ts, value). Mapping tables are at the top of each adapter and are the only part that
changes per county. The pipeline is idempotent: re-running the same export adds nothing."""
import json

from engine.domain import CANCERS, COUNTIES, LANGUAGES, STEPS, fmt_ts, parse_ts

ALLOWED = set(STEPS) | {"stage", "g8", "coordinator", "contact", "booking", "message", "handover", "slip", "report", "open_loop"}
MAX_ROWS = 5000
META_COLS = ("patient_name", "age", "sex", "language", "county", "cancer")


def _key(e):
    return (e["pathway_id"], e["type"], e["ts"], e["value"] or "")


def ingest_events(store, sim, rows, source, by="ingest"):
    """rows: dicts with pathway_id, type, ts, value?, unit? and, for a NEW pathway, patient_name/age/sex/language/county/cancer.
    Returns {added, skipped, created, errors}. Unknown pathways without metadata are rejected, never guessed."""
    if len(rows) > MAX_ROWS:
        raise ValueError(f"too many rows (max {MAX_ROWS})")
    added = skipped = 0
    created, errors, touched = [], [], set()
    with store.lock:
        seen = {_key(e) for pid in {r.get("pathway_id") for r in rows} if pid in store.events for e in store.events[pid]}
        for i, r in enumerate(rows, 1):
            try:
                pid, typ = (r.get("pathway_id") or "").strip(), (r.get("type") or "").strip()
                if not pid or not typ:
                    raise ValueError("pathway_id and type are required")
                if not (typ in ALLOWED or (typ.startswith("pulse:") and typ[6:] in {f"PU{k}" for k in range(1, 11)})):
                    raise ValueError(f"unknown event type {typ!r}")
                ts = fmt_ts(parse_ts(r["ts"]))
                if pid not in store.meta:
                    missing = [c for c in META_COLS if not str(r.get(c) or "").strip()]
                    if missing:
                        raise ValueError(f"new pathway needs {', '.join(missing)}")
                    if r["county"] not in COUNTIES or r["cancer"] not in CANCERS or r["language"] not in LANGUAGES:
                        raise ValueError("county, cancer or language not recognised")
                    store.add_pathway(dict(id=pid, name=r["patient_name"], age=int(r["age"]), sex=r["sex"], language=r["language"], county=r["county"],
                                           cancer=r["cancer"], onset_days=int(r.get("onset_days") or 0), interpreter=r["language"] not in ("fi", "sv", "en")))
                    created.append(pid)
                val = r.get("value") or None
                if val is not None and not isinstance(val, str):
                    val = json.dumps(val, ensure_ascii=False)
                e = dict(pathway_id=pid, type=typ, ts=ts, value=val)
                if _key(e) in seen:
                    skipped += 1
                    continue
                seen.add(_key(e))
                store.append(pid, typ, ts, val, unit=r.get("unit") or None, source=source, entered_by=by)
                touched.add(pid)
                added += 1
            except Exception as ex:
                errors.append(f"row {i}: {ex}")
        from sim import apply as ap
        for pid in touched:
            ap.scan(store, pid, store.vnow)
            sim.schedule(pid)
    return dict(added=added, skipped=skipped, created=created, errors=errors[:50], error_count=len(errors), source=source)
