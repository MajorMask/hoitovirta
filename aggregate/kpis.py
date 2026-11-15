"""County and national KPIs from the event store. Aggregates only; cells with n < min_cell are suppressed (None).
All numbers here are computed from SYNTHETIC events. Benchmarks and targets come from data/evidence.json."""
import random
import statistics

from app import ev
from engine import pulse
from engine.domain import COUNTIES, LANGUAGES, days_between

MIN_CELL = int(ev.v("min_cell"))
TARGET = ev.v("thl_6wk")
EQUITY_FLAG = ev.v("equity_flag")
WINDOW_DAYS = 180


def _median(xs, n=None):
    return round(statistics.median(xs), 1) if len(xs) >= MIN_CELL else None


def _share(num, den):
    return round(100.0 * num / den, 1) if den >= MIN_CELL else None


def views(store, county=None, cancer=None):
    with store.lock:
        return [store.view(pid) for pid in store.ids()
                if (county is None or store.meta[pid]["county"] == county) and (cancer is None or store.meta[pid]["cancer"] == cancer)]


def _recent(now, d):
    return d is not None and days_between(d, now) <= WINDOW_DAYS


def kpis(store, county=None, cancer=None):
    now = store.vnow
    vs = views(store, county, cancer)
    dx = [v for v in vs if v["c1_to_dx"] is not None and _recent(now, v["ts"]["T4"])]
    tx = [v for v in vs if v["t2_to_tx"] is not None and _recent(now, v["ts"]["T6"])]
    staged = [v for v in dx if v["stage"] in ("I", "II", "III", "IV")]
    early = [v for v in staged if v["stage"] in ("I", "II")]
    active = [v for v in vs if not v["done"]]
    loops = sum(1 for v in active if v["open_loop"])
    recent = lambda r: r is not None and days_between(r["ts"], now) <= WINDOW_DAYS
    p4 = [r for r in (pulse.latest(v, "PU4") for v in vs) if recent(r)]
    p5 = [r for r in (pulse.latest(v, "PU5") for v in vs) if recent(r)]
    p7 = [r for r in (pulse.latest(v, "PU7") for v in vs) if recent(r)]
    p9 = [r for r in (pulse.latest(v, "PU9") for v in vs) if recent(r)]
    nps = None
    if len(p9) >= MIN_CELL:
        sc = [float(r["value"]) for r in p9]
        nps = round(100.0 * (sum(1 for x in sc if x >= 9) - sum(1 for x in sc if x <= 6)) / len(sc))
    return dict(
        county=county or "National", cancer=cancer, n_pathways=len(vs), n_active=len(active),
        c1_to_dx_median=_median([v["c1_to_dx"] for v in dx]), t0_to_dx_median=_median([v["t0_to_dx"] for v in dx]), n_dx=len(dx),
        primary_interval_median=_median([v["c1_to_t1"] for v in vs if v["c1_to_t1"] is not None and _recent(now, v["ts"]["T1"])]),
        within_6wk_pct=_share(sum(1 for v in tx if v["t2_to_tx"] <= TARGET), len(tx)), n_tx=len(tx),
        stage_known_pct=_share(len(staged), len(dx)), stage12_pct=_share(len(early), len(staged)), n_staged=len(staged),
        open_loops=loops, open_loops_per100=(round(100.0 * loops / len(active), 1) if len(active) >= MIN_CELL else None),
        informed_pct=_share(sum(1 for r in p4 if r["value"] == "yes"), len(p4)), n_pu4=len(p4),
        reached_1wd_pct=_share(sum(1 for r in p5 if r["value"] == "yes"), len(p5)), n_pu5=len(p5),
        distress_pct=_share(sum(1 for r in p7 if float(r["value"]) >= pulse.DISTRESS_CUTOFF), len(p7)), n_pu7=len(p7),
        nps=nps, n_pu9=len(p9),
        seg_patient=_median([v["onset_days"] for v in dx]),
        seg_primary=_median([v["c1_to_t2"] for v in dx if v["c1_to_t2"] is not None]),
        seg_specialist=_median([v["t2_to_tx"] for v in tx]),
        suppressed_below=MIN_CELL, synthetic=True)


def _range(xs, k=300):
    """10th-90th percentile of the median under resampling: how much a gap could move by chance."""
    if len(xs) < MIN_CELL:
        return None, None
    r = random.Random(1)
    meds = sorted(statistics.median(r.choices(xs, k=len(xs))) for _ in range(k))
    return round(meds[int(0.1 * k)], 1), round(meds[int(0.9 * k)], 1)


def equity_by_language(store, county, cancer=None):
    """Gap in days from first contact to diagnosis by language, adjusted for cancer type: each patient is compared with the
    county median for their own cancer, then the median difference per language is taken. Flag gaps above the evidence threshold."""
    now = store.vnow
    dx = [v for v in views(store, county, cancer) if v["c1_to_dx"] is not None and _recent(now, v["ts"]["T4"])]
    prim = lambda v: v["c1_to_t2"]
    cm = {c: statistics.median([v["c1_to_dx"] for v in dx if v["cancer"] == c]) for c in {v["cancer"] for v in dx}}
    pm = {c: statistics.median([prim(v) for v in dx if v["cancer"] == c and prim(v) is not None]) for c in {v["cancer"] for v in dx if prim(v) is not None}}
    overall = _median([v["c1_to_dx"] for v in dx])
    rows = []
    for code, name in LANGUAGES.items():
        g = [v for v in dx if v["language"] == code]
        raw = _median([v["c1_to_dx"] for v in g])
        res = [v["c1_to_dx"] - cm[v["cancer"]] for v in g]
        gap = _median(res)
        lo, hi = _range(res)
        pgap = _median([prim(v) - pm[v["cancer"]] for v in g if prim(v) is not None])
        rows.append(dict(language=code, name=name, n=len(g), dx_median=raw, gap=gap, primary_gap=pgap, lo=lo, hi=hi,
                         flagged=bool(gap is not None and gap > EQUITY_FLAG and lo is not None and lo > 0)))
    rows.sort(key=lambda r: (r["gap"] is None, -(r["gap"] or 0)))
    return dict(rows=rows, overall=overall, flag_days=EQUITY_FLAG, adjusted_for="cancer type")


def national(store, cancer=None):
    return dict(national=kpis(store, None, cancer), counties=[kpis(store, c, cancer) for c in COUNTIES], cancer=cancer, synthetic=True)
