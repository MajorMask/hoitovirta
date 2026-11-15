"""Per-role metric strips (process playbook section B). Each metric has a value, a target where the playbook gives one, and whether it is met.
Computed from SYNTHETIC events. Targets live in data/evidence.json (ids tgt_*), so the thresholds carry their own status and source."""
import json
import statistics
from datetime import datetime, timezone

from aggregate import kpis as K
from app import ev
from engine.domain import COUNTIES, DOMESTIC, days_between, parse_ts

MIN = K.MIN_CELL


def _med(xs):
    return round(statistics.median(xs), 1) if len(xs) >= MIN else None


def _pct(a, b):
    return round(100.0 * a / b, 1) if b >= MIN else None


def M(id_, value, unit="", target=None, dir_=None, n=None, src=None):
    met = None
    if target is not None and value is not None:
        met = value >= target if dir_ == "ge" else value <= target
    e = ev.get(src) if src else None
    return dict(id=id_, value=value, unit=unit, target=target, dir=dir_, met=met, n=n,
                source=({k: e.get(k) for k in ("id", "claim", "status", "source", "url", "short")} if e else None))


def _tgt(i):
    return ev.v(i)


def _coord_1d(vs):
    xs = [v for v in vs if v["coord_ts"] is not None and v["ts"].get("T0")]
    return M("coord_1d", _pct(sum(1 for v in xs if days_between(v["ts"]["T0"], v["coord_ts"]) <= 1), len(xs)), "%", _tgt("tgt_coord_1d"), "ge", len(xs), "tgt_coord_1d")


def _slips_2d(vs):
    done = tot = 0
    for v in vs:
        for ts, _ in v["slips"]:
            if days_between(ts, v["vnow"]) < 2:
                continue
            tot += 1
            if any(0 <= days_between(ts, b) <= 2 for b, _ in v["bookings"]):
                done += 1
    return M("slips_2d", _pct(done, tot), "%", _tgt("tgt_slip_2d"), "ge", tot, "tgt_slip_2d")


def _interp(vs):
    xs = [v for v in vs if v["language"] in ("ar", "so", "ru")]
    return M("interp", _pct(sum(1 for v in xs if v["interpreter"]), len(xs)), "%", _tgt("tgt_interp"), "ge", len(xs), "tgt_interp")


def _views(store, county):
    with store.lock:
        out = []
        for pid in store.ids():
            if store.meta[pid]["county"] == county:
                v = store.view(pid)
                v["vnow"] = store.vnow
                out.append(v)
        return out


def triage(store, sim, county):
    vs = _views(store, county)
    k = K.kpis(store, county)
    cb = [1 + sum(1 for t in v["contact_ts"] if t < v["ts"]["T1"]) for v in vs if "T1" in v["ts"]]
    third = sum(1 for c in sim.calls.get(county, []) if len(c["prior"]) >= 2)
    return [M("primary_interval", k["primary_interval_median"], "d", n=None), M("contacts", _med(cb), "", _tgt("tgt_contacts"), "le", len(cb), "tgt_contacts"),
            _interp(vs), M("third_waiting", third, "")]


def coordinator(store, county, name):
    vs = _views(store, county)
    own = [v for v in vs if v["coordinator"] == name]
    loops7 = sum(1 for v in own if not v["done"] and v["open_loop"] and days_between(v["open_loop"]["since"], v["vnow"]) >= 7)
    dx = [v["c1_to_dx"] for v in own if v["c1_to_dx"] is not None and K._recent(v["vnow"], v["ts"]["T4"])]
    unassigned = sum(1 for v in vs if not v["done"] and not v["coordinator"])
    return [_coord_1d(vs), M("loops7", loops7, "", _tgt("tgt_loops_7d"), "le", None, "tgt_loops_7d"), M("own_dx", _med(dx), "d", n=len(dx)),
            M("unassigned", unassigned, "", 0, "le"), _slips_2d(vs)]


def diagnostics(store, county):
    from act import reports as R
    items = R._latest(store)
    first = {}
    with store.lock:
        for e in store.log:
            if e["type"] == "report":
                v = json.loads(e["value"])
                first.setdefault(v["report_id"], (v["status"], e["pathway_id"]))
    mine = {rid: s for rid, s in first.items() if store.meta[s[1]]["county"] == county}
    auto = sum(1 for s, _ in mine.values() if s == "saved")
    queue = sum(1 for rid, c in items.items() if c["v"]["status"] == "needs_check" and store.meta[c["event"]["pathway_id"]]["county"] == county)
    flagged = [c for c in items.values() if store.meta[c["event"]["pathway_id"]]["county"] == county and c["v"]["fields"]["suspicious"] and not c["v"]["fields"]["next_step_stated"] and c["v"]["status"] != "needs_check"]
    closed = sum(1 for c in flagged if not store.facts(c["event"]["pathway_id"])["open_loop"])
    k = K.kpis(store, county)
    return [M("queue", queue, ""), M("auto", _pct(auto, len(mine)), "%", _tgt("tgt_auto"), "ge", len(mine), "tgt_auto"),
            M("closed", _pct(closed, len(flagged)), "%", _tgt("tgt_closed"), "ge", len(flagged), "tgt_closed"),
            M("stage_known", k["stage_known_pct"], "%", _tgt("tgt_stage_known"), "ge", k["n_dx"], "tgt_stage_known")]


def screening(store, scr, county, programme):
    from act import outreach as O
    s = O.summary(scr, store.vnow, county, programme)
    parts = [r["participation"] for r in s["rows"] if r["participation"] is not None]
    gap = round(max(parts) - min(parts), 1) if len(parts) >= 2 else None
    # doc 13: FIT+ -> colonoscopy completion (baseline 79%). Completion = a colonoscopy within 60 days of the positive test.
    vs = [v for v in _views(store, county) if v["flag"] == "Positive FIT" and v["ts"].get("T0") and days_between(v["ts"]["T0"], store.vnow) >= 60]
    ok = sum(1 for v in vs if "T3" in v["ts"] and days_between(v["ts"]["T0"], v["ts"]["T3"]) <= 60)
    top = max((m for m in (s["barriers"]["mix"] or [])), key=lambda m: m["count"], default=None)
    out = [M("participation", s["participation"], "%", _tgt("screen_target"), "ge", s["invited"], "screen_target"), M("lang_gap", gap, "pp"),
           M("fit_colon", _pct(ok, len(vs)), "%", _tgt("fit_colonoscopy_79"), "ge", len(vs), "fit_colonoscopy_79")]
    m = M("top_barrier", None)
    m["text"] = top["key"] if top else None
    return out + [m]


def county(store, board, county_name):
    vs = _views(store, county_name)
    state = board.latest(county_name)
    acc = [r for r in state.values() if r["decision"] == "accepted"]
    today = datetime.now(timezone.utc).date().isoformat()
    overdue = sum(1 for r in acc if (r["note"] or "").count("|") and r["note"].split("|")[1] and r["note"].split("|")[1] < today)
    return [M("accepted", len(acc), ""), M("overdue", overdue, "", 0, "le"), _coord_1d(vs), _slips_2d(vs), _interp(vs)]


def national(store):
    rows = [K.kpis(store, c) for c in COUNTIES]
    nat = K.kpis(store)
    have = [r["c1_to_dx_median"] for r in rows if r["c1_to_dx_median"] is not None]
    gap = round(max(have) - min(have), 1) if len(have) >= 2 else None
    return [M("counties", len(have), "", _tgt("counties_21"), "ge", None, "counties_21"), M("regional_gap", gap, "d"),
            M("stage12", nat["stage12_pct"], "%", _tgt("stage_target"), "ge", nat["n_staged"], "stage_target"),
            M("informed", nat["informed_pct"], "%", _tgt("tgt_informed"), "ge", nat["n_pu4"], "tgt_informed")]
