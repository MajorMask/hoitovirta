"""Outreach (screening unit): non-responders by area and language, the barrier mix (Pulse PU3), an SMS in the person's language
(drafted by AI, approved by a person) and a call list. In this demo nothing is really sent. SYNTHETIC data."""
import time
from collections import Counter

from app import llm
from engine.domain import LANGUAGES
from aggregate.kpis import MIN_CELL
from sim.screening import BARRIERS, PROGRAMMES

SMS_EN = {
    "breast": "You are invited to free breast screening. Booking takes 2 minutes: [booking link]. If something makes it hard to come (time, cost, language or worry), reply and we will help.",
    "colorectal": "Your free bowel screening test kit is waiting. It takes 5 minutes at home. If you need a new kit or help, reply or call [clinic number]. If something makes it hard, tell us and we will help.",
}
_cache = {}


def _pct(a, b):
    return round(100.0 * a / b, 1) if b >= MIN_CELL else None


def _states(scr, now, county, programme):
    with scr.lock:
        return [scr.state(i, now) for i, inv in scr.invites.items() if inv["county"] == county and inv["programme"] == programme]


def summary(scr, now, county, programme, language=None):
    st = _states(scr, now, county, programme)
    done = [s for s in st if s["status"] != "pending"]
    scr_n = sum(1 for s in done if s["status"] == "screened")
    non = [s for s in st if s["status"] == "non_responder"]
    rows = []
    for code, name in LANGUAGES.items():
        g = [s for s in done if s["language"] == code]
        gs = sum(1 for s in g if s["status"] == "screened")
        gn = [s for s in non if s["language"] == code]
        rows.append(dict(language=code, name=name, invited=len(g), participation=_pct(gs, len(g)), non_responders=len(gn) if len(gn) >= MIN_CELL else None,
                         contacted=sum(1 for s in gn if s["contacted"])))
    rows.sort(key=lambda r: (r["participation"] is None, r["participation"] or 0))
    pool = [s for s in st if s["barrier"] and (language is None or s["language"] == language)]
    cnt = Counter(s["barrier"] for s in pool)
    barriers = dict(n=len(pool), mix=[dict(key=k, count=cnt.get(k, 0), pct=_pct(cnt.get(k, 0), len(pool))) for k in BARRIERS] if len(pool) >= MIN_CELL else None)
    return dict(county=county, programme=programme, programme_name=PROGRAMMES[programme], invited=len(st), pending=len(st) - len(done),
                participation=_pct(scr_n, len(done)), non_responders=len(non), contacted=sum(1 for s in non if s["contacted"]),
                call_list=sum(1 for s in non if s["on_call_list"]), rows=rows, barriers=barriers, language=language, synthetic=True)


def listing(scr, now, county, programme, language=None, limit=30):
    non = [s for s in _states(scr, now, county, programme) if s["status"] == "non_responder" and (language is None or s["language"] == language)]
    non.sort(key=lambda s: (s["contacted"], -s["days"]))   # not yet contacted first, longest waiting first
    return dict(total=len(non), rows=non[:limit])


def call_list(scr, now, county, programme):
    rows = [s for s in _states(scr, now, county, programme) if s["on_call_list"]]
    rows.sort(key=lambda s: -s["days"])
    return dict(rows=rows)


def draft_sms(programme, language):
    key = (programme, language)
    if key in _cache:
        return _cache[key]
    en = SMS_EN[programme]
    out = dict(programme=programme, language=language, language_name=LANGUAGES[language], text_en=en, text=en, engine="Template", translated=(language == "en"))
    if language != "en":
        t, engine = llm.llm(f"Translate this SMS to {LANGUAGES[language]}. Plain, warm, at most 3 short sentences. Keep anything in [square brackets] exactly as is. "
                            f"Output only the SMS.\n\n{en}", max_tokens=300)
        if t:
            out.update(text=t, engine=engine, translated=True)
    if out["translated"] or language == "en":
        _cache[key] = out
    return out


def send(scr, sim, invite_ids, messages, by):
    """Log an approved SMS per invite and let the simulator produce replies. No real message is sent."""
    sent = Counter()
    now = sim.store.vnow
    with scr.lock:
        ids = [i for i in invite_ids if i in scr.invites and scr.state(i, now)["status"] != "screened"]
        for i in ids:
            lang = scr.invites[i]["language"]
            text = messages.get(lang) or messages.get("en") or SMS_EN[scr.invites[i]["programme"]]
            scr.append(i, "sms_sent", now, dict(programme=scr.invites[i]["programme"], language=lang, text=text, demo=True), by)
            sent[lang] += 1
    sim.schedule_outreach(ids)
    return dict(sent=len(ids), by_language=dict(sent), demo=True)


def add_calls(scr, invite_ids, by, now):
    with scr.lock:
        ids = [i for i in invite_ids if i in scr.invites]
        for i in ids:
            scr.append(i, "call_listed", now, None, by)
    return dict(listed=len(ids))


def mark_called(scr, invite_id, by, now):
    with scr.lock:
        if invite_id not in scr.invites:
            raise KeyError(invite_id)
        scr.append(invite_id, "called", now, None, by)
    return dict(ok=True)
