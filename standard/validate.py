"""Validate an events CSV against the Hoitovirta Pathway Event Standard v1.0 and print the headline KPIs.
Usage:  python standard/validate.py path/to/events.csv        (same columns as ingest/samples/ehr_export.csv)
        python standard/validate.py --sample                  (writes standard/sample_events.csv from a synthetic cohort, then validates it)
Checks: required columns, known event types, parseable UTC timestamps, one pathway = one cancer/county/language, T0 <= T1 <= ... order.
KPIs: median days T0 -> T4 (cells with n < 5 suppressed) and the share treated within 42 days of T2 (THL 21/2016)."""
import csv
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from ingest.ehr_csv import rows_from_csv  # noqa: E402
from ingest.events import ALLOWED  # noqa: E402

STEPS = ["T0", "T1", "T2", "T3", "T4", "T5", "T6"]
MIN_CELL = 5


def parse(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc)


def validate(rows):
    errors, by = [], {}
    for i, r in enumerate(rows, 1):
        try:
            if not (r["type"] in ALLOWED or r["type"].startswith("pulse:")):
                raise ValueError(f"unknown type {r['type']}")
            by.setdefault(r["pathway_id"], []).append((r["type"], parse(r["ts"]), r))
        except Exception as e:
            errors.append(f"row {i}: {e}")
    for pid, evs in by.items():
        seen = {}
        for typ, ts, r in evs:
            if typ in STEPS:
                seen.setdefault(typ, ts)
        order = [seen[s] for s in STEPS if s in seen]
        if order != sorted(order):
            errors.append(f"{pid}: steps are out of order")
    return errors, by


def kpis(by):
    dx, tx = [], []
    for pid, evs in by.items():
        t = {}
        for typ, ts, _ in evs:
            if typ in STEPS:
                t.setdefault(typ, ts)
        if "T0" in t and "T4" in t:
            dx.append((t["T4"] - t["T0"]).total_seconds() / 86400)
        if "T2" in t and "T6" in t:
            tx.append((t["T6"] - t["T2"]).total_seconds() / 86400)
    return dict(n_dx=len(dx), median_t0_to_t4=round(statistics.median(dx), 1) if len(dx) >= MIN_CELL else None,
                n_tx=len(tx), pct_within_42d=round(100 * sum(1 for x in tx if x <= 42) / len(tx), 1) if len(tx) >= MIN_CELL else None)


def make_sample(path):
    import os
    import sqlite3
    os.environ["HV_FORCE_SQLITE"] = "1"
    import app.store as S
    S.LOCAL = Path("/tmp/hv_sample.db")
    S.LOCAL.unlink(missing_ok=True)
    from store.events import EventStore
    from sim import cohort
    from engine.domain import UTC
    st = EventStore()
    cohort.generate(st, datetime.now(UTC))
    out = [["pathway_id", "event_type", "ts", "value", "unit", "patient_name", "age", "sex", "language", "county", "cancer"]]
    for pid in [p for p in st.ids() if p.startswith("PW-0") ][:60]:
        m = st.meta[pid]
        for e in st.events_for(pid):
            if e["type"] in ("T0", "T1", "T2", "T3", "T4", "T5", "T6", "stage", "g8", "coordinator"):
                out.append([pid, e["type"], e["ts"], e["value"] or "", e["unit"] or "", m["name"], m["age"], m["sex"], m["language"], m["county"], m["cancer"]])
    with open(path, "w", newline="") as f:
        csv.writer(f).writerows(out)
    return len(out) - 1


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "--sample"
    if arg == "--sample":
        p = ROOT / "standard" / "sample_events.csv"
        print(f"wrote {make_sample(p)} synthetic events to {p}")
        arg = str(p)
    rows = rows_from_csv(Path(arg).read_text())
    errs, by = validate(rows)
    print(f"{len(rows)} rows, {len(by)} pathways, {len(errs)} problems")
    for e in errs[:20]:
        print("  ", e)
    print("KPIs:", kpis(by), "(synthetic)")
    sys.exit(1 if errs else 0)
