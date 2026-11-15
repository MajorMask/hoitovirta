"""My path (patient): the next step and date, my nurse, my language, "my date slipped", and Pulse questions.
A patient-safe view: no risk scores, no internal flags. Everything a patient sees from staff was approved by a person."""
from app import i18n
from engine import pulse
from act import slots as sl
from engine.domain import CANCER_LABEL, FULLNAME, PLACES, STEPS, UTC
from sim import apply as ap


def _step_key(cancer, step):
    return f"test_{cancer}" if step == "T3" else f"step_{step}"


def view(store, pid):
    with store.lock:
        v = store.view(pid)
        f = store.facts(pid)
        nurse = v["coordinator"] or None
        nxt = v["next_step"]
        # the patient cares about the next real event: the first test, not the internal referral steps
        target = v["booking"]["step"] if v["booking"] else ("T3" if nxt in ("T1", "T2", "T3") else nxt)
        pend = pulse.pending(f, store.vnow)
        last_msg = None
        for ts, m in reversed(f["messages"]):
            if isinstance(m, dict):
                last_msg = dict(ts=ts.isoformat(), text=m.get("text"), language=m.get("language"), nurse=m.get("approved_by"))
                break
        steps = [dict(step=s, state=("done" if s in f["ts"] else ("current" if s == nxt else "todo"))) for s in STEPS]
        return dict(
            pathway_id=pid, first_name=v["name"].split()[0], language=v["language"], interpreter=v["interpreter"], nurse=nurse,
            nurse_full=FULLNAME.get(nurse, nurse), place=PLACES[v["county"]], unit=(f"unit_{sl.KIND[v['cancer']]}" if target == "T3" else None),
            done=v["done"], steps=steps,
            next=(dict(key=_step_key(v["cancer"], target), step=target, due=v["booking"]["due"] if v["booking"] else None,
                       booked=bool(v["booking"])) if target else None),
            slipped=v["slipped"], message=last_msg,
            pulse=(dict(moment=pend["moment"], items=[dict(item=i, kind=pulse.CODEBOOK[i][0], options=pulse.CODEBOOK[i][1]) for i in pend["items"]], conditional=pend.get("conditional", {}), optional=pend.get("optional", [])) if pend else None),
            last_event_id=store.events_for(pid)[-1]["id"], synthetic=True)


def slip(store, sim, pid):
    with store.lock:
        f = store.facts(pid)
        nxt = f["booking"]["step"] if f["booking"] else f["next_step"]
        store.append(pid, "slip", store.vnow, dict(step=nxt, why="Patient reported that the date slipped"), source="patient", entered_by="patient")
        ap.scan(store, pid, store.vnow)
        sim.schedule(pid)
        return dict(ok=True, nurse=f["coordinator"])


def audio_text(store, pid, what, lang):
    """Text to read aloud, limited to the patient's own next step or latest approved message."""
    T, _ = i18n.get(lang)
    with store.lock:
        d = view(store, pid)
        if what == "message":
            return (d["message"] or {}).get("text")
        if not d["next"]:
            return None
        name = T.get(d["next"]["key"], d["next"]["key"])
        if not d["next"]["due"]:
            return f"{T['next']}. {name}. " + T["arranging"].format(nurse=d["nurse"] or "")
        from engine.domain import parse_ts
        due = parse_ts(d["next"]["due"])
        wd = i18n.WEEKDAY.get(lang, i18n.WEEKDAY["en"])[due.weekday()]
        return f"{T['next']}. {name}. {wd}, {due.strftime('%H:%M')}."


URGENT = ("chest pain", "can't breathe", "cannot breathe", "trouble breathing", "heavy bleeding", "bleeding a lot", "suicid", "want to die", "overdose", "faint",
          "rintakipu", "hengitys", "runsas verenvuoto", "itsemurha", "tajunta", "bröstsmärta", "andas inte", "andningssvårigheter", "kraftig blödning", "självmord",
          "ألم في الصدر", "لا أستطيع التنفس", "صعوبة في التنفس", "نزيف", "انتحار", "боль в груди", "не могу дышать", "трудно дышать", "сильное кровотечение", "суицид")


def is_urgent(text):
    low = (text or "").lower()
    return any(k in low for k in URGENT)


def thread(store, pid):
    """The patient's conversation: their questions and the nurse's approved replies, oldest first. A safety net, not a clinical decision."""
    with store.lock:
        f = store.facts(pid)
        items = [dict(who="patient", text=q, ts=t.isoformat()) for t, q in f["questions"]]
        for t, r in f["replies"]:
            if isinstance(r, dict):
                items.append(dict(who="nurse", text=r.get("text"), ts=t.isoformat(), nurse=r.get("approved_by")))
        items.sort(key=lambda i: i["ts"])
        last_q = f["questions"][-1][0] if f["questions"] else None
        answered = [t for t, _ in f["replies"]] + [t for t, _ in f["messages"]] + list(f["calls_out"])
        return dict(items=items, waiting=bool(last_q and (not answered or last_q > max(answered))), nurse=f["coordinator"])


def question(store, sim, pid, text):
    """A patient question: logged on the pathway and raised to the coordinator's list until they call."""
    text = (text or "").strip()[:500]
    if not text:
        raise ValueError("empty question")
    with store.lock:
        store.append(pid, "contact", store.vnow, text, unit="question", source="patient", entered_by="patient")
        sim.schedule(pid)
        return dict(ok=True, nurse=store.facts(pid)["coordinator"], urgent=is_urgent(text))
