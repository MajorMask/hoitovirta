"""14-day breach forecast: how many pathways will pass the 6-week mark (THL 21/2016, referral arrival -> first treatment)
in the next days. Simple and explainable: remaining time per pathway = this county's own median step times
(from completed steps in the last 180 days), plus a chase delay when an open loop is not closed.
A pathway breaches if its projected treatment day falls after the deadline; the soft probability reflects the slack."""
import math
import statistics

from app import ev
from engine.domain import STEPS, days_between
from aggregate.kpis import MIN_CELL, TARGET, WINDOW_DAYS, views

LOOP_DELAY = ev.v("forecast_loop_days")
HORIZON = 14


def step_medians(vs, now):
    """(cancer, step) -> median interval days, from completed steps in the window. Falls back to the cancer's all-county value."""
    iv = {}
    for v in vs:
        for i in range(1, len(STEPS)):
            a, b = STEPS[i - 1], STEPS[i]
            if a in v["ts"] and b in v["ts"] and days_between(v["ts"][b], now) <= WINDOW_DAYS:
                iv.setdefault((v["cancer"], b), []).append(days_between(v["ts"][a], v["ts"][b]))
    return {k: statistics.median(x) for k, x in iv.items() if len(x) >= MIN_CELL}


def _remaining(v, med, loops_closed):
    """Expected days until treatment starts (T6), from now."""
    nxt = v["next_step"]
    if nxt is None:
        return 0.0, 0.0
    i = STEPS.index(nxt)
    first = med.get((v["cancer"], nxt), 8.0)
    if v["booking"]:
        from engine.domain import parse_ts
        first = max(days_between(v["_now"], parse_ts(v["booking"]["due"])), 0.5)
    else:
        first = max(first - v["days_in_step"], 1.0)
        if v["open_loop"] and not loops_closed:
            first += LOOP_DELAY
    rest = [med.get((v["cancer"], s), 8.0) for s in STEPS[i + 1:]]
    to_t2 = first if i <= 2 else 0.0                # time until the clock starts (referral arrival), if not started
    if i <= 2:
        to_t2 = first + sum(med.get((v["cancer"], s), 8.0) for s in STEPS[i + 1:3])
    return first + sum(rest), to_t2


def _p_breach(v, med, loops_closed):
    total, to_t2 = _remaining(v, med, loops_closed)
    t2 = v["ts"].get("T2")
    used = days_between(t2, v["_now"]) if t2 else -to_t2        # negative until the clock starts
    days_to_deadline = TARGET - used if t2 else TARGET + to_t2   # days from now until the 6-week mark
    projected_finish = total
    slack = days_to_deadline - projected_finish
    return 1.0 / (1.0 + math.exp(slack / 5.0)), days_to_deadline


def forecast(store, county, cancer=None):
    now = store.vnow
    allv = views(store, None, cancer)
    med = step_medians([v for v in allv if v["county"] == county], now)
    nat = step_medians(allv, now)
    med = {**nat, **med}                            # county medians where there are enough completed steps
    active = [dict(v, _now=now) for v in allv if v["county"] == county and not v["done"]]
    over, series, series_closed, in_window, loops_in = 0, [0.0] * (HORIZON + 1), [0.0] * (HORIZON + 1), 0, 0
    for v in active:
        p, dtd = _p_breach(v, med, False)
        pc, _ = _p_breach(v, med, True)
        t2 = v["ts"].get("T2")
        if t2 and dtd < 0:
            over += 1
            continue
        if 0 <= dtd <= HORIZON:
            d = int(math.ceil(dtd))
            for k in range(d, HORIZON + 1):
                series[k] += p
                series_closed[k] += pc
            in_window += 1
            loops_in += 1 if v["open_loop"] else 0
    return dict(county=county, cancer=cancer, horizon=HORIZON, already_over=over,
                series=[round(x, 1) for x in series], series_if_loops_closed=[round(x, 1) for x in series_closed],
                expected_14d=round(series[HORIZON], 1), expected_14d_if_closed=round(series_closed[HORIZON], 1),
                pathways_reaching_6wk_in_window=in_window, with_open_loop=loops_in, n_active=len(active),
                method="Projected with this county's median step times; open loops add a chase delay.", synthetic=True)
