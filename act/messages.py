"""Messages: AI drafts, a person approves, the send is logged. AI never decides clinically; it drafts and summarises.
Draft = 2 sentences max, built from facts (offline template), then translated by the LLM chain when the patient's language
is not English. Summary = one line for the coordinator."""
import json
import re
from datetime import timedelta

from app import llm
from app.i18n_staff import loc
from engine.domain import CANCER_LABEL, LANGUAGES, STEPS, fmt_ts, step_name
from act import slots as sl
from sim import apply as ap

_cache = {}


def suggest_booking(store, f, now, slot_id=None):
    """Book the test chain as one sequence: jump to the first test (T3) if it is not done yet, into a reserved slot when one is free."""
    target = "T3" if f["next_step"] in ("T1", "T2", "T3") else f["next_step"]
    label = step_name(f["cancer"], target)
    if target == "T3":
        free = sl.slots(store, f["county"], sl.KIND[f["cancer"]], now)
        chosen = next((s for s in free if s["id"] == slot_id), None) if slot_id else (free[0] if free else None)
        if chosen:
            return dict(step=target, label=label, due=chosen["ts"], when=chosen["when"], slot=chosen["id"], reserved=True)
    due = (now + timedelta(days=2)).replace(hour=10, minute=0, second=0, microsecond=0)
    while due.weekday() >= 5:
        due += timedelta(days=1)
    return dict(step=target, label=label, due=fmt_ts(due), when=f"{due.strftime('%A')} {due.strftime('%H:%M')}", slot=None, reserved=False)


def _digits(s):
    return sorted(re.findall(r"\d+", (s or "").translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))))


def _first_sentence(f):
    flag, cancer, last = f.get("flag"), f["cancer"], f["last_step"]
    if f["slipped"]:
        return "Your appointment moved, and I am sorry."
    if last == "T3" and cancer == "prostate":
        return "Your MRI is done, and the next step is a small tissue sample."
    if last == "T3":
        return "Your test is done, and the next step is to look more closely."
    if flag == "Positive FIT":
        return "Your home test showed a little blood and needs a camera check."
    if flag == "Nodule on X-ray or CT":
        return "The chest X-ray showed a small spot that needs a closer look."
    if flag and flag.startswith("Back or bone"):
        return "You have come to us three times with back pain, so I would like to check your blood."
    return "I want to take the next step in your care without delay."


PHRASE = {("T3", "lung"): "a CT scan", ("T3", "breast"): "your recall imaging", ("T3", "colorectal"): "a colonoscopy",
          ("T3", "prostate"): "an MRI scan", ("T3", "haematological"): "a blood test", ("T4", None): "your diagnosis visit",
          ("T5", None): "your MDT review", ("T6", None): "your treatment start"}


def draft_en(f, booking, coordinator):
    what = PHRASE.get((booking["step"], f["cancer"])) or PHRASE.get((booking["step"], None), booking["label"].lower())
    interp = ", with an interpreter" if f["interpreter"] else ""
    return f"{_first_sentence(f)} I booked {what} for {booking['when']}{interp}, and I will call you tomorrow. — {coordinator}"


def draft_ar(f, booking, coordinator):
    """Offline Arabic wording for the named FIT demo. Keeps the same facts as the English template."""
    if f.get("flag") == "Positive FIT":
        first = "أظهر فحص البراز المنزلي وجود كمية قليلة من الدم، لذلك نحتاج إلى إجراء تنظير للقولون."
    else:
        first = "أريد أن أتابع الخطوة التالية في رعايتك دون تأخير."
    if booking["step"] == "T3" and f["cancer"] == "colorectal":
        what = "تنظير للقولون"
    else:
        what = "الفحص التالي"
    from engine.domain import parse_ts
    weekdays = ("الاثنين", "الثلاثاء", "الأربعاء", "الخميس", "الجمعة", "السبت", "الأحد")
    due = parse_ts(booking["due"])
    when = f"يوم {weekdays[due.weekday()]} الساعة {due.strftime('%H:%M')}"
    interp = "، مع مترجم فوري" if f.get("interpreter") else ""
    return f"{first} حجزت لك {what} {when}{interp}، وسأتصل بك غدًا. — {coordinator}"


def draft(store, pid, staff_lang="en", slot_id=None):
    """Return the draft for the coordinator to review. Cached per pathway state."""
    with store.lock:
        f = store.facts(pid)
        last = store.events_for(pid)[-1]["id"]
        key = ("draft", pid, last, staff_lang, slot_id)
        if key in _cache:
            return _cache[key]
        booking = suggest_booking(store, f, store.vnow, slot_id)
        coordinator = f["coordinator"] or "your nurse"
        en = draft_en(f, booking, coordinator)
        lang, name, interpreter = f["language"], f["name"], f["interpreter"]
    out = dict(pathway_id=pid, language=lang, language_name=LANGUAGES[lang], booking=booking, text_en=en,
               text_local=en if lang == "en" else None, engine="Template", needs_check=False, local_is_english=(lang == "en"))
    if lang != "en":
        prompt = (f"Rewrite this message from a care coordinator to a patient in {LANGUAGES[lang]}. Exactly the same facts, at most 2 sentences "
                  "plus the sign-off, plain and calm. Add no medical advice and no new facts. Keep times and dates as digits exactly as "
                  f"written. Output only the message.\n\n{en}")
        text, engine = llm.llm(prompt, max_tokens=400)
        if text:
            out.update(text_local=text, engine=engine, needs_check=_digits(text) != _digits(en))
        elif lang == "ar":
            out.update(text_local=draft_ar(f, booking, coordinator), engine="Offline template (Arabic)", local_is_english=False)
        else:
            out.update(text_local=en, engine="Offline template (English)", local_is_english=True)
    out["text_staff"] = out["text_en"]
    out["staff_is_english"] = True
    if staff_lang != "en":     # the version the coordinator reads, in the coordinator's language
        names = {"fi": "Finnish", "sv": "Swedish"}
        if out["language"] == staff_lang and out["text_local"] and not out["local_is_english"]:
            out["text_staff"], out["staff_is_english"] = out["text_local"], False
        else:
            t, _ = llm.llm(f"Translate this message to {names[staff_lang]}. Same meaning, no additions. Output only the translation.\n\n{en}", max_tokens=300)
            if t:
                out["text_staff"], out["staff_is_english"] = t, False
    out["booking"] = dict(out["booking"], label_loc=loc(out["booking"]["label"], staff_lang), when_loc=loc(out["booking"]["when"], staff_lang))
    _cache[key] = out
    return out


def reply_draft(store, pid):
    """Draft reply to the patient's open question. A fixed, safe acknowledgement in the patient's language (hand-written, or AI-translated for Somali
    and then checked by a person). The AI does not answer clinical questions; the coordinator can edit the text before approving."""
    from app import i18n
    with store.lock:
        f = store.facts(pid)
        nurse = (f["coordinator"] or "").strip()
        lang = f["language"]
        q = f["questions"][-1] if f["questions"] else None
        answered = [t for t, _ in f["replies"]] + [t for t, _ in f["messages"]] + list(f["calls_out"])
        open_q = bool(q and (not answered or q[0] > max(answered)))
    from engine.domain import FULLNAME
    T, how = i18n.get(lang)
    first = (FULLNAME.get(nurse, nurse) or "").split()[0] or nurse
    return dict(pathway_id=pid, language=lang, language_name=LANGUAGES[lang], question=q[1] if q else None, open=open_q,
                text=T["reply_ack"].format(nurse="— " + first if first else ""), needs_check=(how != "written"),
                engine="Template" if how == "written" else "Machine translated, needs a check")


def reply_send(store, sim, pid, text, language, coordinator):
    """A person approved a written reply: it shows in the patient's thread. No booking, no handover moment."""
    text = (text or "").strip()[:700]
    if not text:
        raise ValueError("empty reply")
    with store.lock:
        who = f"coordinator:{coordinator}"
        store.append(pid, "reply", store.vnow, dict(text=text, language=language, approved_by=coordinator), unit=language, source="act", entered_by=who)
        sim.schedule(pid)
        _cache.clear()
        return dict(ok=True, pathway_id=pid)


def summary(store, pid, staff_lang="en"):
    """One line for the coordinator: who, where they are stuck, why. LLM with an offline template fallback."""
    with store.lock:
        v = store.view(pid)
        last = store.events_for(pid)[-1]["id"]
        key = ("summary", pid, last, staff_lang)
        if key in _cache:
            return _cache[key]
        loop = v["open_loop"]["reason"] if v["open_loop"] else ("date slipped" if v["slipped"] else "none")
        facts = (f"{v['age']}-year-old, {LANGUAGES[v['language']]}{' (interpreter)' if v['interpreter'] else ''}, "
                 f"{CANCER_LABEL[v['cancer']].lower()} pathway, suspicion '{v['flag']}' {int(v['days_total'])} days ago, "
                 f"last step: {v['step_label']} {int(v['days_in_step'])} days ago, open loop: {loop}"
                 f"{', frail (G8 ' + str(int(v['g8'])) + ')' if v['frail'] else ''}.")
        offline = f"{v['age']}, {LANGUAGES[v['language']]}. {CANCER_LABEL[v['cancer']]}: {v['flag'].lower()} {int(v['days_total'])} days ago; {loop}."
        if staff_lang != "en":
            offline = (f"{v['age']} v, {loc(LANGUAGES[v['language']], staff_lang)}. {loc(CANCER_LABEL[v['cancer']], staff_lang)}: {loc(v['flag'], staff_lang).lower()}, "
                       f"{int(v['days_total'])} pv sitten; {loc(loop, staff_lang)}." if staff_lang == "fi" else
                       f"{v['age']} år, {loc(LANGUAGES[v['language']], staff_lang)}. {loc(CANCER_LABEL[v['cancer']], staff_lang)}: {loc(v['flag'], staff_lang).lower()}, "
                       f"för {int(v['days_total'])} dagar sedan; {loc(loop, staff_lang)}.")
    out_lang = {"fi": "Finnish", "sv": "Swedish"}.get(staff_lang, "English")
    text, engine = llm.llm(f"Summarise this pathway for the coordinator in ONE short sentence (max 25 words) in {out_lang}, plain words, no advice, "
                           f"no diagnosis:\n{facts}", max_tokens=120)
    out = dict(pathway_id=pid, text=(text or offline).strip(), engine=engine if text else "Template")
    _cache[key] = out
    return out


def approve(store, sim, pid, text, text_en, language, engine, edited, coordinator, booking):
    """A person approved the message: log it, book the test chain, close the loop, reschedule the simulator."""
    with store.lock:
        f = store.facts(pid)
        now = store.vnow
        who = f"coordinator:{coordinator}"
        # booking the chain as one sequence: referral sent/received happen now if they are still missing
        for s in ("T1", "T2"):
            if STEPS.index(s) < STEPS.index(booking["step"]) and s not in f["ts"]:
                store.append(pid, s, now, step_name(f["cancer"], s), source="coordinator:one-sequence", entered_by=who)
                f = store.facts(pid)
        if booking.get("slot") and not sl.is_free(store, booking["slot"], now):
            raise ValueError("That reserved slot is no longer free")
        store.append(pid, "booking", now, dict(step=booking["step"], due=booking["due"], by=who, slot=booking.get("slot")), source="coordinator", entered_by=who)
        store.append(pid, "message", now, dict(text=text, text_en=text_en, language=language, engine=engine, edited=bool(edited),
                                               booking=booking["label"], when=booking["when"], slot=booking.get("slot"), approved_by=coordinator),
                     unit=language, source="act", entered_by=who)
        ap.scan(store, pid, now)
        sim.schedule(pid)
        _cache.clear()
        return dict(ok=True, pathway_id=pid, open_loop=bool(store.facts(pid)["open_loop"]))


def handover(store, sim, pid, to, note, by):
    with store.lock:
        f = store.facts(pid)
        store.append(pid, "handover", store.vnow, dict(**{"from": f["coordinator"], "to": to}, note=note), source="act", entered_by=f"coordinator:{by}")
        sim.schedule(pid)
        _cache.clear()
        return dict(ok=True, pathway_id=pid, coordinator=to)


def called(store, sim, pid, coordinator):
    """The coordinator called the patient: clears Pulse alerts raised before the call."""
    with store.lock:
        store.append(pid, "contact", store.vnow, "Coordinator call", unit="call-out", source="coordinator-call", entered_by=f"coordinator:{coordinator}")
        sim.schedule(pid)
        return dict(ok=True, pathway_id=pid)
