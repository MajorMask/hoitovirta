"""Three suggested board decisions per county, from simple explainable rules on the county's own aggregates.
The system suggests; the board decides. Every suggestion lists the numbers and sources behind it."""
import statistics
from collections import Counter

from aggregate import kpis as K
from engine.domain import CANCER_LABEL, CANCERS, LANGUAGES, days_between

LOOP_TITLE = [  # (text found in the loop reason, decision)
    ("colonoscopy", "Add colonoscopy slots for positive FITs"),
    ("CT", "Add CT slots for suspected lung cancer"),
    ("SPEP", "Open a vague-symptoms lane for blood cancers (3rd-contact rule)"),
    ("MRI", "Book MRI and biopsy as one sequence"),
    ("biopsy", "Book biopsy with the test result, not after it"),
    ("assessment", "Book the assessment visit when a screen is abnormal"),
    ("slipped", "Give patients a named person to call when a date moves"),
]


def _loop_title(reason):
    for k, t in LOOP_TITLE:
        if k.lower() in reason.lower():
            return t
    return "Name an owner for every handover between steps"


def suggest(store, county, cancer=None):
    vs = K.views(store, county, cancer)
    now = store.vnow
    out = []
    # 1. stalled handovers -> capacity / booking rule
    loops = Counter(v["open_loop"]["reason"] for v in vs if not v["done"] and v["open_loop"])
    if loops:
        reason, n = loops.most_common(1)[0]
        out.append(dict(key="capacity", title=_loop_title(reason), measure="2.5.2",
                        why=[f"{sum(loops.values())} people have an open loop; the most common is “{reason}” ({n})."],
                        evidence=["step_limits", "rm_252"]))
    else:
        out.append(dict(key="capacity", title="Keep the safety-net rule on", measure="2.5.2", why=["No open loops right now."], evidence=["step_limits"]))
    # 2. equity by language
    eq = K.equity_by_language(store, county, cancer)
    flagged = [r for r in eq["rows"] if r["flagged"]]
    if flagged:
        r = flagged[0]
        part = f", {r['primary_gap']} of it before the referral" if r["primary_gap"] is not None and r["primary_gap"] > 0 else ""
        out.append(dict(key="equity", title=f"Interpreter by default for {r['name']} speakers", measure="1.3.1",
                        why=[f"{r['name']} speakers wait {r['gap']} days longer to diagnosis than others with the same cancer{part}.",
                             f"Gaps above {eq['flag_days']} days are flagged."], evidence=["equity_flag"]))
    else:
        top = next((r for r in eq["rows"] if r["gap"] is not None), None)
        out.append(dict(key="equity", title="Keep watching the language gap", measure="1.3.1",
                        why=[f"No language group is more than {eq['flag_days']} days above the county median." + (f" Largest: {top['name']}, {top['gap']} days." if top else "")],
                        evidence=["equity_flag"]))
    # 3. longest wait before the referral arrives -> standard referral criteria + early coordinator
    prim = {}
    for c in CANCERS:
        xs = [v["c1_to_t2"] for v in vs if v["cancer"] == c and v["c1_to_t2"] is not None and "T4" in v["ts"] and days_between(v["ts"]["T4"], now) <= K.WINDOW_DAYS]
        if len(xs) >= K.MIN_CELL:
            prim[c] = round(statistics.median(xs), 1)
    if prim:
        c = max(prim, key=prim.get)
        out.append(dict(key="primary", title=f"Standard referral criteria and a coordinator at first contact: {CANCER_LABEL[c].lower()}", measure="2.5.2",
                        why=[f"{CANCER_LABEL[c]} waits {prim[c]} days from first contact to referral arrival, the longest of the cancers shown.",
                             "Danish fast-track pathways shortened the diagnostic interval (see source)."], evidence=["dk_cpp", "rm_252", "rm_123"]))
    else:
        out.append(dict(key="primary", title="Collect more pathways before deciding on referral criteria", measure="2.5.2",
                        why=["Not enough completed pathways in this view."], evidence=["rm_252"]))
    return out
