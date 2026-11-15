"""Narrow patient companion: event-backed context, guardrails, and a template that works offline."""
import json
import re
import time

from app import llm
from engine.domain import STEP_LABEL, parse_ts
from engine import safety
from voice import journey_guide
from act import mypath

_HISTORY = {}  # pathway id -> [(expiry epoch, role, text)]; short-lived demo conversation state
_MAX_TURNS = 6
_MAX_HISTORY = _MAX_TURNS * 2  # one patient + one guide message per turn
_TTL_SECONDS = 7 * 24 * 60 * 60
_REDIRECT = {
    "en": "That is a question for your doctor or nurse. I can ask the coordinator to call you about it.",
    "fi": "Tuo on kysymys lääkärille tai hoitajalle. Voin pyytää koordinaattoria soittamaan sinulle.",
    "sv": "Det är en fråga för din läkare eller sjuksköterska. Jag kan be samordnaren ringa dig.",
    "ar": "هذا سؤال للطبيب أو الممرضة. يمكنني أن أطلب من منسق الرعاية الاتصال بك.",
    "ru": "На этот вопрос ответит врач или медсестра. Я могу попросить координатора позвонить вам.",
}
_SAFE_NEED = {"info_gap", "transport", "interpreter", "schedule_conflict", "practical_cost", "caregiver_support", "fear_or_distress", "other"}
_ALLOWED_SKILLS = {"prepare", "explain_word", "write_questions", "tell_family", "worried", "after_visit", "notes", "ask_need", "remind", "family_link", "where_am_i", "chat"}
_ALLOWED_INTENTS = {"where_am_i", "prepare", "wait_worry", "glossary", "practical", "feelings", "family", "call_person", "out_of_scope"}
_BLOCK = re.compile(r"\b(?:is this cancer|do i have cancer|what stage|what did (?:my |the )?(?:test|biopsy|scan|result)|(?:test|biopsy) result|what .* biopsy .* show|diagnosis|prognosis|survival rate|am i going to die|how long .* live|dose|medication|medicine|drug|should i take|stop taking|palliative|curative|legal advice|write (?:me )?a poem|translate this essay|ignore (?:all )?(?:previous|prior|your) (?:instructions|rules)|pretend you are|reveal your prompt)\b", re.I)
_BLOCK_LOCAL = re.compile(r"(?:onko (?:minulla|tämä) syöpä|mikä vaihe|diagnoosi|ennuste|elinaika|kuinka kauan elän|lääke|annos|palliatiiv|parantava hoito|är det cancer|har jag cancer|vilket stadium|diagnos|prognos|överlevnad|hur länge lever jag|läkemedel|dos|palliativ|botande behandling|هل هذا سرطان|هل لدي سرطان|ما المرحلة|تشخيص|إنذار المرض|جرعة|دواء|علاج تلطيفي|это рак|у меня рак|какая стадия|диагноз|прогноз|сколько мне жить|доза|лекарств|паллиатив)", re.I)
_CLAIMS = re.compile(r"\b(?:you (?:do not|don't) have cancer|you have cancer|it is cancer|survival rate|life expectancy|you will (?:recover|die|survive)|don't worry|do not worry|everything will be fine|it will be fine|take|stop|start|change|increase|decrease)\b", re.I)
_CLAIMS_LOCAL = re.compile(r"(?:sinulla (?:on|ei ole) syöpä|kaikki järjestyy|ota lääkettä|lopeta lääkkeen|du har cancer|du har inte cancer|allt kommer att ordna sig|ta (?:läkemedel|medicin)|du behöver inte oroa dig|لديك سرطان|ليس لديك سرطان|خذ الدواء|у вас рак|у вас нет рака|примите лекарство)", re.I)
_DATE = re.compile(r"\b(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?|(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|maanantai|tiistai|keskiviikko|torstai|perjantai|måndag|tisdag|onsdag|torsdag|fredag)\b)", re.I)
_TIME = re.compile(r"\b\d{1,2}:\d{2}\b")
_NUMBER = re.compile(r"(?<!\w)\d+(?:[.,]\d+)?(?!\w)")

# Plain-language demo glossary: English, Finnish and Swedish copy is hand-authored here.
# It is a prototype content set and needs clinical/editorial review before real use.
_GLOSSARY = {
    "referral": ("A request for another health service to assess or see you. It does not by itself say what the assessment will find.", "Lähete on pyyntö, että toinen terveyspalvelu arvioi tilanteesi tai ottaa sinut vastaan. Se ei yksin kerro, mitä arvioinnissa todetaan.", "En remiss är en begäran om att en annan vårdtjänst ska bedöma dig eller ta emot dig. Den säger inte i sig vad bedömningen visar."),
    "biopsy": ("A biopsy is a small sample of tissue taken for examination. Your care team explains what the result means.", "Biopsiassa otetaan pieni kudosnäyte tutkittavaksi. Hoitotiimi kertoo, mitä tulos tarkoittaa.", "Vid en biopsi tas ett litet vävnadsprov för undersökning. Vårdteamet förklarar vad resultatet betyder."),
    "mdt": ("A multidisciplinary team is a group of health professionals who discuss care together. Your own team can explain who is involved.", "Moniammatillinen tiimi on joukko terveydenhuollon ammattilaisia, jotka suunnittelevat hoitoa yhdessä. Oma tiimisi kertoo, ketkä siihen kuuluvat.", "Ett multidisciplinärt team är vårdpersonal som diskuterar vården tillsammans. Ditt team kan berätta vilka som deltar."),
    "staging": ("Staging describes how far a cancer has spread, if cancer has been diagnosed. Ask your clinician to explain your own result.", "Levinneisyysaste kuvaa, kuinka laajalle syöpä on levinnyt, jos syöpä on todettu. Pyydä ammattilaista selittämään oma tuloksesi.", "Stadieindelning beskriver hur långt en cancer har spridit sig, om cancer har konstaterats. Be vårdpersonalen förklara ditt resultat."),
    "colonoscopy": ("A colonoscopy is an examination of the large bowel using a flexible camera. Follow the instructions in your appointment letter.", "Kolonoskopia on paksusuolen tutkimus taipuisalla kameralla. Noudata ajanvarauskirjeen ohjeita.", "En koloskopi undersöker tjocktarmen med en böjlig kamera. Följ instruktionerna i din kallelse."),
    "ct": ("A CT scan uses X-rays to make detailed images inside the body. Your clinic tells you whether you need to prepare.", "TT-kuvaus käyttää röntgensäteitä kehon sisäisten kuvien tekemiseen. Klinikka kertoo, pitääkö sinun valmistautua.", "En datortomografi använder röntgenstrålar för detaljerade bilder av kroppen. Kliniken berättar om du behöver förbereda dig."),
    "mri": ("An MRI scan uses a strong magnet and radio waves to make images. Your clinic gives instructions for your appointment.", "Magneettikuvauksessa käytetään vahvaa magneettia ja radioaaltoja kuvien tekemiseen. Klinikka antaa ajan ohjeet.", "En MR-undersökning använder en stark magnet och radiovågor för att skapa bilder. Kliniken ger instruktioner inför besöket."),
    "fit": ("FIT is a stool test that checks for hidden blood. Your care team explains what your result means and what happens next.", "FIT on ulostenäyte, jolla etsitään piilevää verta. Hoitotiimi kertoo, mitä tulos tarkoittaa ja mitä seuraavaksi tapahtuu.", "FIT är ett avföringsprov som letar efter dolt blod. Vårdteamet förklarar vad resultatet betyder och vad som händer sedan."),
    "coordinator": ("A coordinator helps organize the steps in your care path. Your named coordinator is shown in My path when available.", "Koordinaattori auttaa järjestämään hoitopolkusi vaiheita. Nimetty koordinaattori näkyy Minun polkuni -näkymässä, kun tieto on saatavilla.", "En koordinator hjälper till att ordna stegen i din vård. Din koordinator visas i Min vårdväg när uppgiften finns."),
    "pathway": ("A care pathway is the sequence of contacts, tests and appointments for your care. Your own next step is shown in My path.", "Hoitopolku on hoitoosi liittyvien yhteydenottojen, tutkimusten ja aikojen kokonaisuus. Seuraava vaihe näkyy Minun polkuni -näkymässä.", "En vårdväg är ordningen på kontakter, undersökningar och besök i din vård. Nästa steg visas i Min vårdväg."),
    "histology": ("Histology is the examination of tissue under a microscope. Your clinician explains any finding that relates to you.", "Histologiassa tutkitaan kudosta mikroskoopilla. Ammattilainen selittää sinua koskevat löydökset.", "Histologi innebär att vävnad undersöks i mikroskop. Vårdpersonalen förklarar fynd som gäller dig."),
    "lymph node": ("A lymph node is a small part of the body's immune system. Ask your clinician what it means in your situation.", "Imusolmuke on pieni osa kehon puolustusjärjestelmää. Kysy ammattilaiselta, mitä se tarkoittaa tilanteessasi.", "En lymfkörtel är en liten del av kroppens immunförsvar. Fråga vårdpersonalen vad den betyder i din situation."),
    "tumour board": ("A tumour board is a meeting where health professionals discuss a person's care. Your team can tell you how the decision is shared with you.", "Kasvainkokous on tapaaminen, jossa ammattilaiset keskustelevat potilaan hoidosta. Tiimisi kertoo, miten päätöksestä kerrotaan sinulle.", "En multidisciplinär konferens är ett möte där vårdpersonal diskuterar en persons vård. Ditt team berättar hur beslutet förklaras för dig."),
    "radiology": ("Radiology is the use of imaging examinations, such as X-rays or scans, to help assess the body. Your clinician explains your report.", "Radiologia tarkoittaa kuvantamistutkimuksia, kuten röntgen- tai muita kuvauksia. Ammattilainen selittää lausunnon.", "Radiologi använder bilddiagnostik, till exempel röntgen eller andra undersökningar. Vårdpersonalen förklarar utlåtandet."),
    "pathology": ("Pathology examines samples such as tissue or cells. Your care team explains any report about your sample.", "Patologiassa tutkitaan esimerkiksi kudos- tai solunäytteitä. Hoitotiimi selittää näytteestä tehdyn lausunnon.", "Patologi undersöker bland annat vävnads- eller cellprover. Vårdteamet förklarar utlåtandet om ditt prov."),
    "mammogram": ("A mammogram is an X-ray image of the breast. Your appointment letter gives the instructions for the examination.", "Mammografia on rintojen röntgenkuvaus. Ajanvarauskirjeessä ovat tutkimuksen ohjeet.", "Mammografi är en röntgenundersökning av brösten. Kallelsen innehåller instruktioner för undersökningen."),
    "psa": ("PSA is a substance measured in a blood test related to the prostate. Your clinician explains what your own result means.", "PSA on verikokeessa mitattava eturauhaseen liittyvä aine. Ammattilainen kertoo, mitä oma tuloksesi tarkoittaa.", "PSA är ett ämne som mäts i ett blodprov och har samband med prostatan. Vårdpersonalen förklarar ditt resultat."),
    "referral accepted": ("This means the receiving service has recorded the referral. It does not tell you the result of any examination.", "Tämä tarkoittaa, että vastaanottava palvelu on kirjannut lähetteen. Se ei kerro tutkimusten tuloksista.", "Det betyder att mottagande vårdtjänst har registrerat remissen. Det säger inget om undersökningsresultat."),
    "appointment": ("An appointment is a planned time to meet or have an examination. Check your care letter for location and preparation instructions.", "Ajanvaraus on sovittu aika tapaamiselle tai tutkimukselle. Tarkista hoitokirjeestä paikka ja valmistautumisohjeet.", "En bokad tid är ett planerat besök eller en undersökning. Kontrollera plats och förberedelser i kallelsen."),
    "interpreter": ("An interpreter helps you and health professionals understand each other. You can ask your coordinator whether one is arranged.", "Tulkki auttaa sinua ja ammattilaisia ymmärtämään toisianne. Voit kysyä koordinaattorilta, onko tulkki järjestetty.", "En tolk hjälper dig och vårdpersonalen att förstå varandra. Fråga koordinatorn om en tolk har ordnats."),
    "open loop": ("An open loop means a planned next step is not yet recorded as complete or booked. Your coordinator can check what is needed.", "Avoin vaihe tarkoittaa, että seuraavaa sovittua vaihetta ei ole vielä kirjattu valmiiksi tai varatuksi. Koordinaattori voi tarkistaa tilanteen.", "En öppen punkt betyder att nästa planerade steg ännu inte har registrerats som klart eller bokat. Koordinatorn kan kontrollera läget."),
    "treatment": ("Treatment is care chosen by the clinical team for a person's situation. Ask your clinician to explain any treatment decision.", "Hoito on kliinisen tiimin tilanteeseen valitsemaa hoitoa. Pyydä ammattilaista selittämään hoitopäätös.", "Behandling är vård som det kliniska teamet väljer för personens situation. Be vårdpersonalen förklara beslutet."),
    "diagnosis": ("A diagnosis is a clinician's conclusion about a health condition after assessment. Your clinician is the right person to explain yours.", "Diagnoosi on ammattilaisen arvio sairaudesta tutkimusten jälkeen. Oma ammattilaisesi selittää diagnoosisi.", "En diagnos är vårdpersonalens bedömning av ett hälsotillstånd efter undersökning. Din vårdpersonal förklarar din diagnos."),
    "scan": ("A scan creates images of part of the body. Your clinic explains which scan is planned and how to prepare.", "Kuvauksessa tehdään kuvia kehon osasta. Klinikka kertoo, mikä kuvaus on suunniteltu ja miten siihen valmistaudutaan.", "En bilddiagnostisk undersökning skapar bilder av en del av kroppen. Kliniken berättar vilken undersökning som planeras och hur du ska förbereda dig."),
    "blood test": ("A blood test examines a sample of blood. Your care team explains why it is planned and what the result means.", "Verikokeessa tutkitaan verinäyte. Hoitotiimi kertoo, miksi koe on suunniteltu ja mitä tulos tarkoittaa.", "Ett blodprov undersöker ett blodprov. Vårdteamet berättar varför provet planeras och vad resultatet betyder."),
    "care team": ("Your care team is the group of people involved in your care. My path shows the coordinator when one has been assigned.", "Hoitotiimi koostuu hoitoosi osallistuvista ihmisistä. Minun polkuni näyttää koordinaattorin, kun hänet on nimetty.", "Ditt vårdteam är personerna som deltar i din vård. Min vårdväg visar koordinatorn när en har utsetts."),
}


def _language(lang):
    return lang if lang in {"fi", "sv", "en", "ar", "ru"} else "en"


def _typed_language(text, preferred):
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"
    if re.search(r"[А-Яа-яЁё]", text):
        return "ru"
    low = text.lower()
    if re.search(r"\b(jag|min|nästa|vad|sjuksköterska|bröstsmärta|andningssvårigheter|är det|har jag)\b", low):
        return "sv"
    if re.search(r"\b(hoitaja|mitä|seuraava|olen|pelottaa|rintakipu|hengitysvaikeus|soita)\b", low):
        return "fi"
    if re.search(r"\b(what|where|when|how|my|i am|i have|next|appointment|biopsy|help|scared|worried|nurse|call|bring|should|drug|dose|cancer|results|stage|die)\b", low):
        return "en"
    return _language(preferred)


def _context(store, pid, lang):
    """Only use the patient's My path view and the matching public guide entry."""
    d = mypath.view(store, pid)
    stage = journey_guide.stage_for(store, pid)
    guide = journey_guide.get_guide(stage, lang)
    nxt = d.get("next") or {}
    due = nxt.get("due")
    date_friendly = None
    days_until_next = None
    if due:
        try:
            dt = parse_ts(due)
            if store.vnow:
                days_until_next = int((dt - store.vnow).total_seconds() / 86400)
            weekdays = {
                "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
                "fi": ("maanantai", "tiistai", "keskiviikko", "torstai", "perjantai", "lauantai", "sunnuntai"),
                "sv": ("måndag", "tisdag", "onsdag", "torsdag", "fredag", "lördag", "söndag"),
            }
            months = {"en": ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"),
                      "fi": ("tammikuuta", "helmikuuta", "maaliskuuta", "huhtikuuta", "toukokuuta", "kesäkuuta", "heinäkuuta", "elokuuta", "syyskuuta", "lokakuuta", "marraskuuta", "joulukuuta"),
                      "sv": ("januari", "februari", "mars", "april", "maj", "juni", "juli", "augusti", "september", "oktober", "november", "december")}
            dl = lang if lang in weekdays else "en"
            date_friendly = f"{weekdays[dl][dt.weekday()]} {dt.day} {months[dl][dt.month - 1]} {dt.year} at {dt:%H:%M}" if dl == "en" else f"{weekdays[dl][dt.weekday()]} {dt.day} {months[dl][dt.month - 1]} {dt.year} {dt:%H:%M}"
        except (TypeError, ValueError):
            date_friendly = None
    notes = []
    for event in store.events.get(pid, []):
        if event["type"] == "patient_note" and event.get("value"):
            try:
                value = json.loads(event["value"])
                notes.append(value.get("text", ""))
            except (TypeError, ValueError):
                continue
    context = {
        "patient_first_name": d.get("first_name"),
        "language": lang,
        "stage": STEP_LABEL.get(stage, stage.replace("_", " ")),
        "next_step": {"test_colorectal": "Colonoscopy", "test_lung": "CT scan", "test_breast": "Recall imaging",
                      "test_prostate": "MRI scan", "test_haematological": "Blood test"}.get(nxt.get("key"), nxt.get("key")),
        "date": nxt.get("due"),
        "date_friendly": date_friendly,
        "days_until_next": days_until_next,
        "patient_notes": notes[-3:],
        "place": d.get("place"),
        "nurse_first_name": (d.get("nurse") or "").split()[0] or None,
        "interpreter": bool(d.get("interpreter")),
        "journey_guide": {k: guide.get(k) for k in ("what_is_happening", "today_you_can", "ask_these", "who_to_call", "myths")},
    }
    return context


def _template(context, lang, intent="where_am_i"):
    lang = _language(lang)
    nurse = context.get("nurse_first_name")
    nxt = context.get("next_step")
    date = context.get("date_friendly") or context.get("date")
    place = context.get("place")
    if intent == "call_person":
        if nurse:
            reply = {"en": f"Your nurse is {nurse}. You can call the care team using the number on this page.",
                     "fi": f"Hoitajasi on {nurse}. Voit soittaa hoitotiimille tällä sivulla näkyvään numeroon.",
                     "sv": f"Din sjuksköterska är {nurse}. Du kan ringa vårdteamet på numret på den här sidan."}[lang]
        else:
            reply = {"en": "I do not have a nurse name here. I can ask the coordinator to contact you.",
                     "fi": "En näe tässä hoitajan nimeä. Voin pyytää koordinaattoria ottamaan yhteyttä.",
                     "sv": "Jag ser inget namn på en sjuksköterska här. Jag kan be samordnaren kontakta dig."}[lang]
        return _result(reply, "call_person", "ask_coordinator", ["call_nurse", "ask_coordinator"], ["pathway:nurse"] if nurse else [])
    if intent == "prepare":
        guide = context.get("journey_guide") or {}
        text = guide.get("today_you_can") or guide.get("ask_these")
        if text:
            reply = str(text).split(". ")[0].rstrip(".") + "."
        else:
            reply = _unknown(lang)
        return _result(reply, "prepare", "none" if text else "ask_coordinator", ["ask_coordinator"] if not text else [], ["guide:current_stage"] if text else [])
    if intent == "where_am_i" and nxt:
        labels = {"en": f"Your next step is {nxt}.", "fi": f"Seuraava vaiheesi on {nxt}.", "sv": f"Nästa steg är {nxt}."}
        parts = [labels[lang]]
        if date:
            parts.append({"en": f"The date shown is {date}.", "fi": f"Näytetty aika on {date}.", "sv": f"Tiden som visas är {date}."}[lang])
        if place:
            parts.append({"en": f"The place is {place}.", "fi": f"Paikka on {place}.", "sv": f"Platsen är {place}."}[lang])
        return _result(" ".join(parts), "where_am_i", "none" if date else "ask_coordinator", [] if date else ["ask_coordinator"], ["pathway:next_step"] + (["pathway:date"] if date else []) + (["pathway:place"] if place else []))
    return _result(_unknown(lang), "wait_worry", "ask_coordinator", ["ask_coordinator"], [])


def _unknown(lang):
    return {"en": "I do not have that detail here. I can ask the coordinator to contact you.",
            "fi": "En näe tätä tietoa tässä. Voin pyytää koordinaattoria ottamaan yhteyttä.",
            "sv": "Jag ser inte den uppgiften här. Jag kan be samordnaren kontakta dig."}[_language(lang)]


def _loc(lang, en, fi, sv):
    return {"en": en, "fi": fi, "sv": sv}.get(lang, en)


def _result(reply, intent, escalate, buttons, sources, need=None, provider="template", elapsed_ms=0):
    return dict(reply=reply, intent=intent, need=need, escalate=escalate, sources=sources,
                need_suggestion=None, offer_buttons=buttons, provider=provider, elapsed_ms=int(elapsed_ms),
                skill=None, cards=[], follow_ups=[], save_note=None, language_note=None, advisory=False)


def _prompt(context, text, lang, history):
    examples = (
        "Tone examples: acknowledge briefly, give a fact only from context, then one next step. "
        "Fear: 'That is a lot to carry. The next step is the one shown in your plan. I can ask your nurse to call.' "
        "Family: speak to the family member in second person and use only the patient's context. "
        "Never copy an example date or name unless it appears in the supplied context."
    )
    # list every allowed value: a model that is only told "one allowed intent" invents names ("preparation", "pathway_status") and the reply is thrown away
    contract = {"reply": "string", "intent": "where_am_i|prepare|wait_worry|glossary|practical|feelings|family|call_person|out_of_scope",
                "need": "null or one of info_gap|transport|interpreter|schedule_conflict|practical_cost|caregiver_support|fear_or_distress|other",
                "escalate": "none|ask_coordinator|callback_today|emergency",
                "sources": ["only from: pathway:next_step, pathway:date, pathway:place, pathway:nurse, pathway:interpreter, guide:current_stage"],
                "offer_buttons": ["only from: call_nurse, ask_nurse, ask_coordinator, book_interpreter"]}
    return (f"You are a narrow patient care-path guide, not a doctor. Scope: pathway status, preparation, waiting, plain meanings, practical needs, feelings, family support, or reaching a person. Refuse diagnosis, test results, prognosis, drugs, doses, treatment instructions, legal advice and unrelated requests. Use only the context. No exclamation marks. At most 3 short sentences. Reply in {lang}. Output JSON only matching this contract: {json.dumps(contract)}. {examples}\n"
            f"Context pack: {json.dumps(context, ensure_ascii=False)}\nRecent conversation: {json.dumps(history[-_MAX_HISTORY:], ensure_ascii=False)}\nUser: {text}")


def _parse(raw):
    if not raw:
        return None
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw.strip(), flags=re.I)
    try:
        return json.loads(cleaned)
    except (ValueError, TypeError):
        return {"reply": cleaned}


def _grounded(reply, context):
    flat = json.dumps(context, ensure_ascii=False)
    for pattern in (_DATE, _TIME, _NUMBER):
        for token in pattern.findall(reply):
            if token not in flat:
                return False
    nurse = context.get("nurse_first_name")
    # Reject named care staff or places not present in the supplied pack.
    candidates = re.findall(r"\b[A-Z][a-z]+(?:[ -][A-Z][a-z]+)+\b", reply)
    allowed = [str(context.get(k) or "") for k in ("patient_first_name", "place", "nurse_first_name")]
    if any(candidate not in allowed and candidate not in flat for candidate in candidates):
        return False
    if nurse and re.search(r"\b(?:Laura|Mikko|Aisha|Petra|Omar|Elina|Sanna|Jussi|Fatima|Heidi|Antti|Noora|Anne|Tuomas|Saara)\b", reply):
        return nurse in reply
    return True


def _validate(raw_obj, context, fallback_intent="where_am_i"):
    if not isinstance(raw_obj, dict) or not isinstance(raw_obj.get("reply"), str):
        return None
    if "intent" not in raw_obj:                       # plain text is not the JSON contract: still falls back to the template
        return None
    reply = raw_obj["reply"].strip()
    intent = raw_obj.get("intent")
    need = raw_obj.get("need")
    escalate = raw_obj.get("escalate", "none")
    buttons = raw_obj.get("offer_buttons", [])
    sources = raw_obj.get("sources", [])
    # The reply text is checked strictly below. The labels around it are metadata: an invented intent, need, button or source id is repaired
    # (intent from the keyword guess, the rest dropped) instead of discarding a good, grounded answer. A need is only ever used from the safe list.
    if intent not in _ALLOWED_INTENTS:
        intent = fallback_intent
    if need not in _SAFE_NEED:
        need = None
    if escalate not in {"none", "ask_coordinator", "callback_today", "emergency"}:
        escalate = "none"
    if not isinstance(buttons, list):
        buttons = []
    buttons = [b for b in buttons if b in {"call_nurse", "ask_coordinator", "ask_nurse", "book_interpreter"}]
    allowed_sources = {"pathway:next_step", "pathway:date", "pathway:place", "pathway:nurse", "pathway:interpreter", "guide:current_stage"}
    sources = [s for s in sources if isinstance(s, str) and s in allowed_sources] if isinstance(sources, list) else []
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", reply) if s]
    if not reply or "!" in reply or len(sentences) > 3 or _CLAIMS.search(reply) or _CLAIMS_LOCAL.search(reply) or not _grounded(reply, context):
        return None
    if intent == "out_of_scope":
        return _result(_REDIRECT[_language(context.get("language"))], "out_of_scope", "ask_coordinator", ["ask_coordinator"], [], provider="policy")
    if need:
        buttons = ["ask_nurse"] + [b for b in buttons if b != "ask_nurse"]
    result = _result(reply, intent, escalate, buttons[:3], sources[:6])
    result["need_suggestion"] = need
    return result


def _skill_result(store, pid, context, skill, arg, lang):
    guide = context.get("journey_guide") or {}
    result = None
    if skill == "prepare":
        items = [guide.get("today_you_can") or guide.get("ask_these", [""])[0]]
        if context.get("place"):
            items.append({"en": f"Place: {context['place']}", "fi": f"Paikka: {context['place']}", "sv": f"Plats: {context['place']}"}.get(lang, f"Place: {context['place']}"))
        items.append({"en": "Interpreter: arranged" if context.get("interpreter") else "Interpreter: not shown as arranged; ask your coordinator if you need one.",
                      "fi": "Tulkki: järjestetty" if context.get("interpreter") else "Tulkki: ei näy järjestettynä. Pyydä tarvittaessa koordinaattoria järjestämään tulkki.",
                      "sv": "Tolk: ordnad" if context.get("interpreter") else "Tolk: visas inte som ordnad. Be koordinatorn ordna en om du behöver."}.get(lang, "Interpreter: ask your coordinator if you need one."))
        items.append({"en": "Follow your clinic letter for preparation. Ask the clinic about clinical instructions.",
                      "fi": "Noudata klinikan kirjettä. Kysy klinikalta tutkimukseen valmistautumisesta.",
                      "sv": "Följ instruktionerna från kliniken. Fråga kliniken om förberedelser."}.get(lang, "Follow your clinic letter; ask the clinic about preparation."))
        name = (context.get("patient_first_name") or "").strip()
        greet = {"en": f"{name}, we can take the next step one piece at a time." if name else "We can take the next step one piece at a time.",
                 "fi": f"{name}, voimme käydä seuraavan vaiheen läpi yksi asia kerrallaan." if name else "Voimme käydä seuraavan vaiheen läpi yksi asia kerrallaan.",
                 "sv": f"{name}, vi kan ta nästa steg en sak i taget." if name else "Vi kan ta nästa steg en sak i taget."}.get(lang, "I can help with the practical details.")
        result = _result(greet, "prepare", "none", [], ["guide:current_stage"])
        result.update(cards=[dict(kind="checklist", title={"en": "Before your next step", "fi": "Ennen seuraavaa vaihetta", "sv": "Inför nästa steg"}.get(lang, "Before your next step"), items=[x for x in items if x])],
                      follow_ups=[dict(label=_loc(lang, "Remind me", "Muistuta minua", "Påminn mig"), skill="remind", arg=None), dict(label=_loc(lang, "I need a ride", "Tarvitsen kyydin", "Jag behöver skjuts"), skill="ask_need", arg="transport")])
    elif skill == "explain_word":
        term = str(arg or "").strip().lower().strip(" ?.!:")
        term = re.sub(r"^(what is|what does|explain|mitä tarkoittaa|vad betyder)\s+", "", term)
        found = next((key for key in _GLOSSARY if key == term or key in term), None)
        if not found:
            reply = _unknown(lang)
            result = _result(reply, "out_of_scope", "ask_coordinator", ["ask_coordinator"], [])
            result["follow_ups"] = [dict(label=_loc(lang, "Ask my nurse", "Kysy hoitajalta", "Fråga sjuksköterskan"), skill="ask_need", arg="info_gap")]
        else:
            idx = {"en": 0, "fi": 1, "sv": 2}.get(lang, 0)
            definition = _GLOSSARY[found][idx]
            result = _result(definition, "glossary", "none", [], ["guide:glossary"])
            result["cards"] = [dict(kind="definition", title=found, items=[definition])]
            if lang in ("ar", "ru"):
                result["language_note"] = "Machine translated"
                result["provider"] = "template (English glossary fallback)"
    elif skill == "write_questions":
        questions = list(guide.get("ask_these") or [])[:3]
        if arg:
            questions.append(str(arg).strip()[:140])
        questions = questions[:5]
        result = _result(_loc(lang, "Here are a few questions you could take to your visit.", "Tässä on muutama kysymys, jonka voit ottaa mukaan vastaanotolle.", "Här är några frågor du kan ta med till besöket."), "prepare", "none", [], ["guide:current_stage"])
        result.update(cards=[dict(kind="questions", title=_loc(lang, "Questions for my visit", "Kysymykset vastaanotolle", "Frågor till besöket"), items=questions)], save_note={"text": "\n".join(questions)})
    elif skill == "tell_family":
        bits = [context.get("next_step") or _loc(lang, "the next step", "seuraava vaihe", "nästa steg")]
        if context.get("date_friendly"):
            bits.append(context["date_friendly"])
        if context.get("place"):
            bits.append(context["place"])
        when = f" on {bits[1]}" if len(bits) > 1 else ""
        where = f" at {bits[2]}" if len(bits) > 2 else ""
        drafts = {
            "en": f"My next step is {bits[0]}{when}{where}. I do not have a result to share here. You can help by coming with me or helping me write down questions.",
            "fi": f"Seuraava vaiheeni on {bits[0]}{(' ' + bits[1]) if len(bits) > 1 else ''}{(', paikassa ' + bits[2]) if len(bits) > 2 else ''}. Minulla ei ole tässä tulosta jaettavaksi. Voit auttaa tulemalla mukaan tai auttamalla kysymysten kirjaamisessa.",
            "sv": f"Mitt nästa steg är {bits[0]}{(' ' + bits[1]) if len(bits) > 1 else ''}{(', på ' + bits[2]) if len(bits) > 2 else ''}. Jag har inget resultat att dela här. Du kan hjälpa genom att följa med eller skriva ner frågor tillsammans med mig.",
        }
        result = _result(_loc(lang, "I can draft a simple update using only your care plan.", "Voin laatia lyhyen viestin hoitosuunnitelmasi tietojen perusteella.", "Jag kan skriva ett kort meddelande utifrån din vårdplan."), "family", "none", [], ["pathway:next_step"] + (["pathway:date"] if context.get("date_friendly") else []) + (["pathway:place"] if context.get("place") else []))
        result["cards"] = [dict(kind="draft", title=_loc(lang, "A message to share", "Jaettava viesti", "Ett meddelande att dela"), items=[drafts.get(lang, drafts["en"])])]
        result["follow_ups"] = [dict(label=_loc(lang, "Open family view", "Avaa läheisnäkymä", "Öppna familjevyn"), skill="family_link", arg=None)]
    elif skill == "worried":
        step = {"en": "Your next step is shown in My path.", "fi": "Seuraava vaihe näkyy Minun polkuni -näkymässä.", "sv": "Nästa steg visas i Min vårdväg."}.get(lang, "Your next step is shown in My path.")
        result = _result({"en": "That sounds like a lot to carry. Take one slow breath, then notice four things around you. " + step,
                          "fi": "Tuo voi tuntua paljolta. Hengitä rauhallisesti ja huomaa sitten neljä asiaa ympärilläsi. " + step,
                          "sv": "Det kan kännas mycket. Ta ett lugnt andetag och lägg sedan märke till fyra saker omkring dig. " + step}.get(lang, "I can stay with you for one small step."), "feelings", "none", [], ["pathway:next_step"])
        result["cards"] = [dict(kind="steps", title=_loc(lang, "Choose what would help", "Valitse, mikä auttaisi", "Välj det som skulle hjälpa"), items=[_loc(lang, "Ask my nurse to call me", "Pyydä hoitajaa soittamaan", "Be sjuksköterskan ringa mig"), _loc(lang, "What happens next", "Mitä tapahtuu seuraavaksi", "Vad händer sedan"), _loc(lang, "Keep chatting", "Jatka keskustelua", "Fortsätt prata")])]
        result["follow_ups"] = [dict(label=_loc(lang, "Ask my nurse to call", "Pyydä hoitajaa soittamaan", "Be sjuksköterskan ringa"), skill="ask_need", arg="fear_or_distress"), dict(label=_loc(lang, "What happens next", "Mitä tapahtuu seuraavaksi", "Vad händer sedan"), skill="where_am_i", arg=None), dict(label=_loc(lang, "Keep chatting", "Jatka keskustelua", "Fortsätt prata"), skill="chat", arg=None)]
        if str(arg or "").isdigit() and 0 <= int(arg) <= 10:
            store.append(pid, "pulse:PU7", store.vnow, str(int(arg)), unit="companion_worry", source="companion", entered_by="patient")
        result["advisory"] = bool(str(arg or "").isdigit() and int(arg) >= 7)
    elif skill == "after_visit":
        choice = str(arg or "").lower()
        if choice in {"fine", "confusing", "hard"}:
            value = "yes" if choice == "fine" else "no"
            store.append(pid, "pulse:PU4", store.vnow, value, unit="after_visit", source="companion", entered_by="patient")
            result = _result({"en": "Thank you for telling us. You can add a private note if you want.", "fi": "Kiitos kun kerroit. Voit halutessasi lisätä yksityisen muistiinpanon.", "sv": "Tack för att du berättade. Du kan lägga till en privat anteckning om du vill."}.get(lang, "Thank you for telling us."), "feelings", "none", [], ["pulse:PU4"])
            result["save_note"] = {"text": f"After visit: {choice}"}
            if choice != "fine":
                result["need_suggestion"] = "info_gap"
                result["offer_buttons"] = ["ask_nurse"]
                result["follow_ups"] = [dict(label=_loc(lang, "Ask my nurse to explain", "Pyydä hoitajaa selittämään", "Be sjuksköterskan förklara"), skill="ask_need", arg="info_gap")]
        else:
            result = _result(_loc(lang, "How did the visit go?", "Miten käynti sujui?", "Hur gick besöket?"), "feelings", "none", [], [])
            labels = {"fine": _loc(lang, "Fine", "Hyvin", "Bra"), "confusing": _loc(lang, "Confusing", "Epäselvästi", "Oklart"), "hard": _loc(lang, "Hard", "Vaikeasti", "Svårt")}
            result["cards"] = [dict(kind="steps", title=_loc(lang, "Choose one", "Valitse yksi", "Välj ett"), items=list(labels.values()))]
            result["follow_ups"] = [dict(label=labels[x], skill="after_visit", arg=x) for x in ("fine", "confusing", "hard")]
    elif skill == "notes":
        notes = context.get("patient_notes") or []
        result = _result(_loc(lang, "Your notes are private unless you choose to share one.", "Muistiinpanosi ovat yksityisiä, ellet päätä jakaa niitä.", "Dina anteckningar är privata om du inte väljer att dela dem."), "where_am_i", "none", [], [])
        result["cards"] = [dict(kind="steps", title=_loc(lang, "My recent notes", "Viimeisimmät muistiinpanot", "Mina senaste anteckningar"), items=notes[-3:] or [_loc(lang, "No notes saved yet.", "Ei tallennettuja muistiinpanoja.", "Inga anteckningar sparade ännu.")])]
    elif skill == "ask_need":
        need = str(arg or "other")
        if need not in _SAFE_NEED:
            need = "other"
        result = _result(_loc(lang, "Would you like me to ask your nurse to contact you?", "Haluatko, että pyydän hoitajaa ottamaan yhteyttä?", "Vill du att jag ber sjuksköterskan kontakta dig?"), "practical", "ask_coordinator", ["ask_nurse"], [])
        result["need_suggestion"] = need
    elif skill == "remind":
        store.append(pid, "companion_reminder", store.vnow, {"step": context.get("next_step"), "due": context.get("date")}, source="companion", entered_by="patient")
        result = _result(_loc(lang, "A reminder request was saved for your next step.", "Muistutuspyyntö seuraavasta vaiheesta tallennettiin.", "En påminnelse om nästa steg sparades."), "prepare", "none", [], ["pathway:next_step"])
    elif skill == "family_link":
        result = _result(_loc(lang, "Use the family link shown in My path and share it only with someone you trust.", "Käytä Minun polkuni -näkymän läheislinkkiä ja jaa se vain luotettavalle henkilölle.", "Använd familjelänken i Min vårdväg och dela den bara med någon du litar på."), "family", "none", [], [])
    elif skill == "where_am_i":
        result = _template(context, lang, "where_am_i")
    elif skill == "chat":
        result = _result(_unknown(lang), "where_am_i", "ask_coordinator", ["ask_coordinator"], [])
    return result


def _translate_skill(result, context, lang, started):
    """Ask the configured provider chain to translate skill copy; retain English if validation fails."""
    if lang not in ("ar", "ru"):
        return result
    source = {"reply": result["reply"], "cards": result.get("cards", []), "follow_ups": result.get("follow_ups", [])}
    prompt = (f"Translate the human-readable text in this JSON into {'Arabic' if lang == 'ar' else 'Russian'}. Preserve every fact, name, date, number, action key, and card kind exactly. Do not add content. Output JSON only with the same keys and structure.\n"
              f"Pathway context for grounding: {json.dumps(context, ensure_ascii=False)}\nJSON: {json.dumps(source, ensure_ascii=False)}")
    try:
        raw, provider = llm.llm(prompt, system="Translate faithfully. Do not provide medical advice.", max_tokens=360, deadline=started + 8)
        translated = _parse(raw)
        valid = (isinstance(translated, dict) and isinstance(translated.get("reply"), str)
                 and isinstance(translated.get("cards"), list) and isinstance(translated.get("follow_ups"), list)
                 and _grounded(translated["reply"], context) and "!" not in translated["reply"]
                 and not _CLAIMS.search(translated["reply"]) and not _CLAIMS_LOCAL.search(translated["reply"])
                 and len(translated["cards"]) == len(source["cards"])
                 and len(translated["follow_ups"]) == len(source["follow_ups"]))
        if valid:
            for before, after in zip(source["cards"], translated["cards"]):
                if (not isinstance(after, dict) or after.get("kind") != before.get("kind")
                        or not isinstance(after.get("title"), str) or not isinstance(after.get("items"), list)
                        or len(after["items"]) != len(before.get("items", []))
                        or any(not isinstance(item, str) or "!" in item or not _grounded(item, context) or _CLAIMS.search(item) or _CLAIMS_LOCAL.search(item) for item in [after["title"], *after["items"]])):
                    valid = False
                    break
            for before, after in zip(source["follow_ups"], translated["follow_ups"]):
                if not isinstance(after, dict) or after.get("skill") != before.get("skill") or after.get("arg") != before.get("arg") or not isinstance(after.get("label"), str):
                    valid = False
                    break
        if valid:
            result.update(reply=translated["reply"], cards=translated["cards"], follow_ups=translated["follow_ups"], provider=provider, language_note="Machine translated")
            return result
    except Exception:
        pass
    result["language_note"] = "English fallback"
    return result


def companion_reply(store, pid, text=None, lang="en", history=None, skill=None, arg=None):
    """Respond from one pathway only. The urgent pre-filter runs before guide/model calls."""
    started = time.perf_counter()
    preferred_lang = lang
    lang = _typed_language(text or "", lang)
    english_fallback = preferred_lang == "so" and lang == "en"
    text = (text or "").strip()[:500]
    if not text and not skill:
        result = _result(_unknown(lang), "where_am_i", "ask_coordinator", ["ask_coordinator"], [], provider="template")
        if english_fallback:
            result["language_note"] = "English fallback"
        return result
    lower = text.lower()
    if safety.is_urgent(text):
        self_harm = safety.is_self_harm(text)
        reply = safety.patient_message(lang, self_harm=self_harm)
        store.append(pid, "companion_asked", store.vnow, {"intent": "emergency", "escalate": "callback_today"}, source="companion", entered_by="patient")
        store.append(pid, "need", store.vnow, {"need": "callback_today", "source": "companion"}, source="companion", entered_by="patient")
        store.add_task(pid, "callback", "Patient companion emergency pre-filter: call back today", assigned_to=store.facts(pid).get("coordinator"))
        return _result(reply, "feelings", "emergency", ["call_nurse"], ["policy:emergency"], need="fear_or_distress", provider="policy", elapsed_ms=(time.perf_counter()-started)*1000)

    # Do not pass medical or unrelated requests to a model.
    if _BLOCK.search(text) or _BLOCK_LOCAL.search(text) or (skill == "explain_word" and (_BLOCK.search(str(arg or "")) or _BLOCK_LOCAL.search(str(arg or "")))):
        result = _result(_REDIRECT[lang], "out_of_scope", "ask_coordinator", ["ask_coordinator"], [], provider="policy")
        if english_fallback:
            result["language_note"] = "English fallback"
        _record(store, pid, result, started)
        return result

    if skill and skill not in _ALLOWED_SKILLS:
        raise ValueError("unknown companion skill")
    context = _context(store, pid, lang)
    if skill:
        skilled = _skill_result(store, pid, context, skill, arg, lang)
        if skilled:
            skilled["skill"] = skill
            skilled = _translate_skill(skilled, context, lang, started)
            if english_fallback:
                skilled["language_note"] = "English fallback"
            _record(store, pid, skilled, started)
            return skilled
    hist = list(history or _history_for(pid))[-_MAX_HISTORY:]
    intent = "call_person" if re.search(r"\b(?:call|speak to|talk to|hoitaj|soita|ring|prata med)\b", lower) else ("prepare" if re.search(r"\b(?:bring|prepare|what to take|mitä ottaa|ta med)\b", lower) else "where_am_i")
    chosen = None
    provider = "template"
    # Existing common LLM chain, with one correction attempt. Each call is budgeted in app.llm.
    for _ in range(2):
        try:
            raw, provider = llm.llm(_prompt(context, text, lang, hist), system="Return only the requested JSON. Do not reveal reasoning.", max_tokens=220, deadline=started + 8)
        except Exception:
            raw = None
        parsed = _parse(raw)
        chosen = _validate(parsed, context, intent)
        if chosen:
            if chosen["provider"] != "policy":
                chosen["provider"] = provider
            break
    if not chosen:
        chosen = _template(context, lang, intent)
        provider = "template"
    if chosen["provider"] != "policy":
        chosen["provider"] = provider
    chosen["elapsed_ms"] = int((time.perf_counter()-started)*1000)
    chosen["skill"] = skill or intent
    if lang in ("ar", "ru"):
        chosen["language_note"] = "Machine translated" if provider not in ("template", "offline") else "English fallback"
    elif lang == "so":
        chosen["language_note"] = "English fallback"
    _remember(pid, "user", text)
    _remember(pid, "assistant", chosen["reply"])
    _record(store, pid, chosen, started)
    return chosen


def _history_for(pid):
    now = time.time()
    rows = [(role, text) for expiry, role, text in _HISTORY.get(pid, []) if expiry > now]
    _HISTORY[pid] = [(now + _TTL_SECONDS, role, text) for role, text in rows]
    return rows[-_MAX_HISTORY:]


def _remember(pid, role, text):
    rows = _history_for(pid)
    rows.append((role, text))
    _HISTORY[pid] = [(time.time() + _TTL_SECONDS, r, t) for r, t in rows[-_MAX_HISTORY:]]


def _record(store, pid, result, started):
    store.append(pid, "companion_asked", store.vnow, {"intent": result["intent"], "need_suggestion": result.get("need_suggestion"), "escalate": result["escalate"], "provider": result["provider"]}, source="companion", entered_by="patient")
    result["elapsed_ms"] = int((time.perf_counter() - started) * 1000)


def confirm_need(store, pid, need):
    """Create a need event and nurse task only after explicit patient confirmation."""
    if need not in _SAFE_NEED:
        raise ValueError("unknown companion need")
    store.append(pid, "need", store.vnow, {"need": need, "confirmed": True}, source="companion", entered_by="patient")
    coordinator = store.facts(pid).get("coordinator")
    task = store.add_task(pid, "patient_need", f"Patient requested companion support: {need}", assigned_to=coordinator)
    return {"ok": True, "pathway_id": pid, "need": need, "task_id": task["id"]}
