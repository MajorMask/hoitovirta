"""Reserved (ring-fenced) diagnostic slots: the Fast-diagnosis lane. Imaging and endoscopy keep slots for suspected cancer and the
coordinator books the test chain into them. SYNTHETIC capacity: two slots per test type, county and working day; some are already
used by other suspected-cancer patients, so capacity is visible and can run short."""
import hashlib
import json
from datetime import timedelta

from app import ev
from engine.domain import fmt_ts, parse_ts

KIND = {"lung": "ct", "breast": "imaging", "colorectal": "colonoscopy", "prostate": "mri", "haematological": "lab"}
TIMES = ("08:30", "13:00")
PER_DAY = int(ev.v("slots_per_day"))
HORIZON_DAYS = 10
OCCUPIED_PCT = 35     # share of reserved slots already used by other patients (synthetic)


def _occupied(slot_id):
    return int(hashlib.md5(slot_id.encode()).hexdigest(), 16) % 100 < OCCUPIED_PCT


def _taken_by_us(store):
    out = set()
    with store.lock:
        for e in store.log:
            if e["type"] == "booking" and e["value"] and '"slot"' in e["value"]:
                try:
                    s = json.loads(e["value"]).get("slot")
                    if s:
                        out.add(s)
                except Exception:
                    pass
    return out


def slots(store, county, kind, now, free_only=True, limit=12):
    taken = _taken_by_us(store)
    out, day = [], (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    for _ in range(HORIZON_DAYS):
        if day.weekday() < 5:
            for t in TIMES[:PER_DAY]:
                h, m = map(int, t.split(":"))
                ts = day.replace(hour=h, minute=m)
                sid = f"{county[:3]}-{kind}-{ts.strftime('%Y%m%dT%H%M')}"
                busy = _occupied(sid) or sid in taken
                if busy and free_only:
                    continue
                out.append(dict(id=sid, ts=fmt_ts(ts), when=f"{ts.strftime('%A')} {t}", free=not busy, kind=kind))
        day += timedelta(days=1)
    return out[:limit]


def free_counts(store, county, now):
    return {k: len(slots(store, county, k, now, limit=999)) for k in ("ct", "imaging", "colonoscopy", "mri", "lab")}


def is_free(store, slot_id, now):
    from engine.domain import COUNTIES
    try:
        prefix, kind, _ = slot_id.split("-", 2)
    except ValueError:
        return False
    county = next((c for c in COUNTIES if c[:3] == prefix), None)
    return bool(county) and any(s["id"] == slot_id for s in slots(store, county, kind, now, limit=999))
