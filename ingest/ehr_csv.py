"""EHR export CSV adapter. One row per event. Columns (header names are matched case-insensitively; the aliases map a county's own
export headings to ours, so adding a county means adding aliases here, not code):
  pathway_id, event_type, ts, value, unit, patient_name, age, sex, language, county, cancer, onset_days
Event types are the Hoitovirta codes: T0 (suspicion), T1 (referral sent), T2 (referral received), T3 (first test), T4 (diagnosis),
T5 (MDT), T6 (first treatment), stage, g8, coordinator, contact. S0 and C1 are derived, never stored."""
import csv
import io

ALIASES = {"type": ["event_type", "event", "tapahtuma", "type"], "ts": ["ts", "timestamp", "datetime", "aika", "date"],
           "pathway_id": ["pathway_id", "episode_id", "pseudo_id", "potilas_id"], "value": ["value", "arvo"], "unit": ["unit", "yksikko"],
           "patient_name": ["patient_name", "name", "nimi"], "age": ["age", "ika"], "sex": ["sex", "sukupuoli"], "language": ["language", "kieli"],
           "county": ["county", "hyvinvointialue"], "cancer": ["cancer", "syopa"], "onset_days": ["onset_days"]}


def rows_from_csv(text):
    rdr = csv.DictReader(io.StringIO(text))
    if not rdr.fieldnames:
        raise ValueError("empty CSV")
    cols = {f.strip().lower(): f for f in rdr.fieldnames}
    pick = {k: next((cols[a] for a in al if a in cols), None) for k, al in ALIASES.items()}
    for need in ("pathway_id", "type", "ts"):
        if not pick[need]:
            raise ValueError(f"missing column for {need} (accepted: {', '.join(ALIASES[need])})")
    return [{k: (row.get(c) if c else None) for k, c in pick.items()} for row in rdr]
