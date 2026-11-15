"""Worklists: pathways ranked by breach risk and vulnerability, one reason per row."""
import time

from app import ev
from engine import pulse, risk, rules
from engine.domain import CANCER_LABEL, LANGUAGES, STEPS, STEP_LABEL, step_name, days_between, parse_ts


FIRST_CALL = ev.v("first_call_days")
FIT_DAYS = int(ev.v("fit_14d"))
REF_DAYS = ev.v("referral_accept_days")


def row(store, pid):
    v = store.view(pid)
    prob, reasons = risk.score(v)
    vuln = rules.vulnerability(v)
    loop = v["open_loop"]
    booking = v["booking"]
    booking_view = None
    if booking:
        due = booking.get("due")
        try:
            when = parse_ts(due).strftime("%A %H:%M") if due else None
        except (TypeError, ValueError):
            when = None
        booking_view = dict(due=due, slot=booking.get("slot"), when=when, reserved=bool(booking.get("slot")))
    fresh = (not v["messages"]) and v["days_total"] < FIRST_CALL and not v["done"]
    pin = (not v["messages"]) and (time.time() - store.human_new.get(pid, 0) < 1800)
    al = pulse.alerts(v, store.vnow)
    priority = 0.7 * prob + 0.3 * vuln + (0.15 if loop else 0.0) + (0.4 if fresh else 0.0) + (0.5 if al else 0.0)
    top = [t for _, t in reasons[:2]]
    if fresh:
        top.insert(0, f"New fast-track: first call within {int(FIRST_CALL)} days")
    if al:
        top = [a["text"] for a in al] + top
    reason = al[0]["text"] if al else (f"Open loop: {loop['reason']}" if loop else (top[0] if top else "On track"))
    return dict(id=pid, name=v["name"], age=v["age"], language=v["language"], language_name=LANGUAGES[v["language"]],
                interpreter=v["interpreter"], county=v["county"], cancer=v["cancer"], cancer_label=CANCER_LABEL[v["cancer"]],
                coordinator=v["coordinator"], day=int(v["days_total"]), step=v["last_step"], step_label=v["step_label"],
                next_label=v["next_label"], risk=round(prob, 3), vulnerability=round(vuln, 2), open_loop=bool(loop),
                loop_reason=loop["reason"] if loop else None, target_days=(FIT_DAYS if (v["cancer"] == "colorectal" and v["last_step"] in ("T0", "T1", "T2")) else None), new=fresh, pin=pin, alert=bool(al), alerts=[a["text"] for a in al], slipped=v["slipped"], frail=v["frail"], reason=reason,
                reasons=top, priority=round(priority, 3), done=v["done"], flag=v["flag"], flag_label=v["flag"], stage=v["stage"], booking=booking_view, slot=booking.get("slot") if booking else None)


def worklist(store, coordinator, limit=8):
    with store.lock:
        rows = [row(store, pid) for pid in store.ids()
                if store.facts(pid)["coordinator"] == coordinator and not store.facts(pid)["done"]]
    rows.sort(key=lambda r: (not (r["pin"] or r["alert"]), -r["priority"]))  # new fast-tracks and Pulse alerts need a call: pinned on top
    tasks = store.pending_tasks(assigned_to=coordinator)
    return dict(coordinator=coordinator, total=len(rows), open_loops=sum(r["open_loop"] for r in rows), rows=rows[:limit], tasks=tasks)


def detail(store, pid):
    with store.lock:
        v = store.view(pid)
        base = row(store, pid)
        t0 = v["ts"].get("T0")
        steps = []
        cur = v["last_step"]
        for s in STEPS:
            ts = v["ts"].get(s)
            state = "done" if ts else ("current" if s == v["next_step"] else "todo")
            steps.append(dict(step=s, label=step_name(v["cancer"], s), ts=ts.isoformat() if ts else None,
                              day=int(days_between(t0, ts)) if ts and t0 else None, state=state,
                              booked=(v["booking"]["due"] if v["booking"] and v["booking"]["step"] == s else None)))
        # Patient notes are private unless the patient explicitly shares them through the notes endpoint.
        evs = [e for e in store.events_for(pid) if e["type"] != "patient_note"]
        t1, t2 = v["ts"].get("T1"), v["ts"].get("T2")
        if not t1:
            ref = dict(state="none")
        elif t2:
            w_ = days_between(t1, t2)
            ref = dict(state="accepted" if w_ <= REF_DAYS else "accepted_late", days=int(w_), target=int(REF_DAYS))
        else:
            w_ = days_between(t1, store.vnow)
            ref = dict(state="waiting" if w_ <= REF_DAYS else "overdue", days=int(w_), target=int(REF_DAYS))
        f = store.facts(pid)
        answered = [t for t, _ in f["replies"]] + [t for t, _ in f["messages"]] + list(f["calls_out"])
        lq = f["questions"][-1] if f["questions"] else None
        base["open_question"] = lq[1] if lq and (not answered or lq[0] > max(answered)) else None
        base.update(referral=ref, questions=[dict(ts=t.isoformat(), text=q) for t, q in v["questions"]], steps=steps, onset_days=v["onset_days"], g8=v["g8"], coordinator_name=v["coordinator"],
                    contacts=[dict(ts=t.isoformat(), value=val) for t, val in v["contacts"]],
                    booking=v["booking"], days_in_step=round(v["days_in_step"], 1),
                    messages=[dict(ts=t.isoformat(), **(m if isinstance(m, dict) else dict(text=m))) for t, m in v["messages"]],
                    last_event_id=evs[-1]["id"] if evs else 0,
                    history=[dict(id=e["id"], ts=e["ts"], type=e["type"], value=e["value"], by=e["entered_by"]) for e in evs[-14:]][::-1])
        return base
