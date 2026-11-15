"""Standalone, synthetic-only Pulse check-in and feedback loop.

Run from the repository root with:
    uvicorn pulse_service.main:app --host 127.0.0.1 --port 8011

This service does not import or write to the Hoitovirta event store. Responses
and mock follow-up tasks live in memory and disappear when the process stops.
"""
from __future__ import annotations

import json
import pathlib
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field


ROOT = pathlib.Path(__file__).resolve().parent.parent
STATIC = pathlib.Path(__file__).resolve().parent / "static"
EVIDENCE = ROOT / "data" / "evidence.json"


def distress_evidence() -> dict:
    """Read the existing sourced cut-off; do not invent a fallback value."""
    try:
        rows = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        entry = next(row for row in rows if row.get("id") == "distress_cutoff")
        value = int(entry["value"])
        if entry.get("status") != "sourced" or not 0 <= value <= 10 or not entry.get("url"):
            raise ValueError("distress evidence is incomplete")
        return {"value": value, "source": entry["url"], "claim": entry["claim"]}
    except (OSError, ValueError, KeyError, TypeError, StopIteration, json.JSONDecodeError) as exc:
        raise RuntimeError("Cannot load sourced distress threshold from data/evidence.json") from exc


DISTRESS = distress_evidence()

# This is deliberately a two-question suspicion moment, copied from the
# shared Pulse codebook. Patient copy uses the existing app translations.
COPY = {
    "fi": {
        "name": "Suomi", "title": "Miten voit tänään?", "intro": "Vastauksesi auttaa hoitotiimiäsi tukemaan sinua.",
        "q4": "Tiedätkö, mitä seuraavaksi tapahtuu?", "q7": "Kuinka huolissasi olet ollut tällä viikolla?",
        "scale": "0 = ei lainkaan · 10 = erittäin", "yes": "Kyllä, tiedän", "unsure": "En ole varma", "no": "En vielä",
        "thanks": "Kiitos, että kerroit.", "call": "Hoitajasi pyytää sinulle yhteydenoton tänään tai seuraavana arkipäivänä.",
        "clarify": "Hoitotiimisi saa pyynnön selventää seuraavaa vaihetta.", "ok": "Vastauksesi on tallennettu tähän mock-kyselyyn.",
        "submit": "Lähetä vastaukset", "again": "Aloita uusi mock-vastaus", "foot": "Prototyyppi · synteettinen data",
        "staff": "Hoitotiimin mock-palautelista", "empty": "Ei avointa seurantapyyntöä.", "open": "Avoin yhteydenottopyyntö",
        "closed": "Valmis mock-seuranta", "close": "Merkitse mock-yhteydenotto tehdyksi", "done": "Mock-yhteydenotto merkitty tehdyksi.",
        "source": "Raja-arvon lähde", "privacy": "Älä kirjoita tähän oikeaa nimeä tai terveystietoja. Tämä erillinen prototyyppi ei tallenna vastauksia pysyvästi.",
    },
    "sv": {
        "name": "Svenska", "title": "Hur mår du i dag?", "intro": "Dina svar hjälper vårdteamet att ge dig stöd.",
        "q4": "Vet du vad som händer härnäst?", "q7": "Hur orolig har du varit den här veckan?",
        "scale": "0 = inte alls · 10 = mycket", "yes": "Ja, jag vet", "unsure": "Jag är osäker", "no": "Inte ännu",
        "thanks": "Tack för att du berättade.", "call": "Din sjuksköterska ber att få kontakta dig i dag eller nästa vardag.",
        "clarify": "Vårdteamet får en begäran om att förklara nästa steg.", "ok": "Ditt svar har sparats i den här testenkäten.",
        "submit": "Skicka svar", "again": "Börja ett nytt testsvar", "foot": "Prototyp · syntetiska data",
        "staff": "Vårdteamets testlista för återkoppling", "empty": "Ingen öppen begäran om uppföljning.", "open": "Öppen begäran om kontakt",
        "closed": "Avslutad testuppföljning", "close": "Markera testkontakten som gjord", "done": "Testkontakten har markerats som gjord.",
        "source": "Källa för gränsvärdet", "privacy": "Skriv inte in ditt riktiga namn eller hälsouppgifter. Den här fristående prototypen sparar inte svar permanent.",
    },
    "en": {
        "name": "English", "title": "How are you feeling today?", "intro": "Your answers help your care team support you.",
        "q4": "Do you know what happens next?", "q7": "How worried have you been this week?",
        "scale": "0 = not at all · 10 = extremely", "yes": "Yes, I know", "unsure": "I am not sure", "no": "Not yet",
        "thanks": "Thank you for telling us.", "call": "Your nurse would request a call today or the next working day.",
        "clarify": "Your care team would receive a request to clarify the next step.", "ok": "Your answers were saved in this mock survey.",
        "submit": "Send answers", "again": "Start another mock response", "foot": "Prototype · synthetic data",
        "staff": "Care-team mock feedback queue", "empty": "No open follow-up request.", "open": "Open call-back request",
        "closed": "Mock follow-up completed", "close": "Mark mock call-back complete", "done": "Mock follow-up marked complete.",
        "source": "Threshold source", "privacy": "Do not enter a real name or health details. This separate prototype does not store responses permanently.",
    },
}

# Canonical Pulse item and moment keys from docs/PULSE-INSTRUMENT.md and
# engine/pulse.py. Text stays optional and bounded; the service does not infer.
ITEMS = {
    "PU1": {"kind": "choice", "options": ["week", "w2_4", "m1_3", "m3p"]},
    "PU2": {"kind": "choice", "options": ["1", "2", "3p"]},
    "PU3": {"kind": "choice", "options": ["time", "cost", "language", "fear", "noappt", "notserious"]},
    "PU4": {"kind": "choice", "options": ["yes", "unsure", "no"]},
    "PU5a": {"kind": "choice", "options": ["yes", "no", "not_tried"]},
    "PU5": {"kind": "choice", "options": ["yes", "no"]},
    "PU6": {"kind": "choice", "options": ["yes", "partly", "no"]},
    "PU7": {"kind": "scale", "options": [str(i) for i in range(11)]},
    "PU8": {"kind": "choice", "options": ["0", "1", "2", "3p"]},
    "PU9": {"kind": "scale", "options": [str(i) for i in range(11)]},
    "PU9b": {"kind": "text", "options": ["skip"], "max_length": 500},
    # two mock extras for the screening check-in: not part of the validated Pulse instrument, labelled as such in the page
    "SX1": {"kind": "choice", "options": ["yes", "unsure", "no"]},
    "SX2": {"kind": "choice", "options": ["reminder", "evening", "ride", "call", "nothing"]},
}
MOMENT_ITEMS = {
    "first_contact": ["PU1", "PU2"], "suspicion": ["PU4", "PU7"],
    "handover": ["PU4", "PU5a"], "diagnosis": ["PU9", "PU7"],
    "treatment": ["PU9", "PU8"],
    "screening": ["PU3", "PU4"],          # people invited to free screening: what makes it hard (PU3, docs/PULSE-INSTRUMENT.md), do you know what happens next
}
SCREENING_EXTRAS = {"SX1", "SX2"}


def validate_answers(moment: str, answers: dict[str, Any]) -> dict[str, Any]:
    """Validate only the moment's canonical items, conditional PU5, optional PU9b."""
    required = list(MOMENT_ITEMS[moment])
    if moment == "first_contact" and "PU6" in answers:
        required = ["PU1", "PU6"]
    if moment == "handover" and answers.get("PU5a") == "yes":
        required.append("PU5")
    optional = {"PU9b"} if moment in ("diagnosis", "treatment") else (set(SCREENING_EXTRAS) if moment == "screening" else set())
    allowed = set(required) | optional
    unknown = set(answers) - allowed
    missing = set(required) - set(answers)
    if unknown or missing:
        raise HTTPException(status_code=422, detail={"unknown": sorted(unknown), "missing": sorted(missing)})
    clean = {}
    for code, value in answers.items():
        spec = ITEMS[code]
        if spec["kind"] == "text":
            value = str(value).strip()
            if value != "skip" and (not value or len(value) > spec["max_length"]):
                raise HTTPException(status_code=422, detail=f"invalid {code}")
        elif str(value) not in spec["options"]:
            raise HTTPException(status_code=422, detail=f"invalid {code}")
        else:
            value = int(value) if code in ("PU7", "PU9") else str(value)
        clean[code] = value
    if moment != "handover" and "PU5" in clean:
        raise HTTPException(status_code=422, detail="PU5 is only valid at handover")
    if moment == "handover" and clean.get("PU5a") != "yes" and "PU5" in clean:
        raise HTTPException(status_code=422, detail="PU5 requires PU5a=yes")
    return clean


app = FastAPI(title="Hoitovirta Pulse · mock service", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
_lock = threading.Lock()
_responses: list[dict] = []
_tasks: list[dict] = []


class Answers(BaseModel):
    """Patient-reported answers only; no names or clinical inference."""
    model_config = ConfigDict(extra="forbid")
    demo_case: str = Field(pattern=r"^DEMO-[A-Z0-9-]{1,32}$")
    language: Literal["fi", "sv", "en"] = "fi"
    moment: Literal["first_contact", "suspicion", "handover", "diagnosis", "treatment", "screening"]
    channel: Literal["app", "web", "phone"] = "app"
    answers: dict[str, Any] = Field(default_factory=dict)

    # Backwards compatibility for the first suspicion-moment UI fixture.
    PU4: Literal["yes", "unsure", "no"] | None = None
    PU7: int | None = Field(default=None, ge=0, le=10)


class CompleteTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    done: bool = True


@app.get("/health")
def health():
    return {"ok": True, "service": "pulse-mock", "synthetic": True}


@app.get("/api/instrument")
def instrument(language: Literal["fi", "sv", "en"] = "fi"):
    return {
        "service": "pulse-mock",
        "synthetic": True,
        "moment": "suspicion",
        "moments": {k: list(v) for k, v in MOMENT_ITEMS.items()},
        "items": {k: ITEMS[k] for k in MOMENT_ITEMS["suspicion"]},
        "questions_per_moment": 2,
        "estimated_seconds": 20,
        "distress_cutoff": DISTRESS["value"],
        "distress_source": DISTRESS["source"],
        "sources": [
            {"label": "NCCN Distress Thermometer", "claim": DISTRESS["claim"], "url": DISTRESS["source"]},
            {"label": "Hoitovirta Pulse item definitions and schedule", "reference": "docs/PULSE-INSTRUMENT.md"},
            {"label": "Process measures and event definitions", "reference": "the process playbook"},
        ],
        "copy": COPY[language],
    }


@app.post("/api/responses")
def submit_response(answer: Answers):
    submitted = dict(answer.answers)
    if answer.PU4 is not None:
        submitted.setdefault("PU4", answer.PU4)
    if answer.PU7 is not None:
        submitted.setdefault("PU7", answer.PU7)
    values = validate_answers(answer.moment, submitted)
    now = datetime.now(timezone.utc).isoformat()
    signals = []
    if values.get("PU7") is not None and int(values["PU7"]) >= DISTRESS["value"]:
        signals.append("distress_follow_up")
    if values.get("PU4") in ("unsure", "no"):
        signals.append("clarify_next_step")
    if values.get("PU5") == "no":
        signals.append("nurse_not_reached_within_1_working_day")
    if values.get("PU3") in ("time", "cost", "language", "noappt"):
        signals.append("screening_barrier")            # a practical barrier the screening unit can act on (the Outreach screen)
    if values.get("SX1") in ("unsure", "no"):
        signals.append("explain_free_screening")
    if values.get("SX2") in ("reminder", "evening", "ride", "call"):
        signals.append("offer_help")

    response_id = "RESP-" + uuid.uuid4().hex[:10].upper()
    task = None
    if signals:
        task = {
            "id": "TASK-" + uuid.uuid4().hex[:8].upper(),
            "response_id": response_id,
            "demo_case": answer.demo_case,
            "language": answer.language,
            "created_at": now,
            "signals": signals,
            "status": "open",
            "due": "today_or_next_working_day" if "distress_follow_up" in signals else "care_team_review",
            "synthetic": True,
        }

    row = {
        "id": response_id, "demo_case": answer.demo_case, "moment": answer.moment,
        "language": answer.language, "channel": answer.channel, "answers": values,
        "items": [{"item_code": code, "value": value, "unit": "text" if code == "PU9b" else ITEMS[code]["kind"]}
                  for code, value in values.items()],
        "signals": signals, "created_at": now, "synthetic": True,
    }
    with _lock:
        _responses.append(row)
        if task:
            _tasks.append(task)

    patient_copy = COPY[answer.language]
    follow_up = patient_copy["call"] if "distress_follow_up" in signals else (
        patient_copy["clarify"] if "clarify_next_step" in signals else patient_copy["ok"]
    )
    if answer.moment == "screening":
        follow_up = SCREEN_COPY[answer.language]["followup"] if signals else SCREEN_COPY[answer.language]["ok"]
    return {
        "response": row,
        "feedback": {"message": patient_copy["thanks"], "follow_up": follow_up, "task_created": bool(task)},
        "source": {"claim": DISTRESS["claim"], "url": DISTRESS["source"], "value": DISTRESS["value"]},
        "synthetic": True,
    }


@app.get("/api/feedback")
def feedback_queue(language: Literal["fi", "sv", "en"] = "fi"):
    with _lock:
        tasks = [dict(task) for task in reversed(_tasks)]
        rows = [dict(row) for row in _responses]
        count = len(rows)
        open_count = sum(task["status"] == "open" for task in _tasks)
    informed_rows = [row for row in rows if "PU4" in row["answers"]]
    distress_rows = [row for row in rows if "PU7" in row["answers"]]
    nps_rows = [row for row in rows if "PU9" in row["answers"]]
    reached_rows = [row for row in rows if row["answers"].get("PU5a") == "yes" and "PU5" in row["answers"]]
    metrics = {
        "respondents": count,
        "informed_share_pct": round(100 * sum(row["answers"]["PU4"] == "yes" for row in informed_rows) / len(informed_rows), 1) if len(informed_rows) >= 5 else None,
        "informed_respondents": len(informed_rows) if len(informed_rows) >= 5 else None,
        "distress_at_or_above_cutoff_share_pct": round(100 * sum(row["answers"]["PU7"] >= DISTRESS["value"] for row in distress_rows) / len(distress_rows), 1) if len(distress_rows) >= 5 else None,
        "distress_respondents": len(distress_rows) if len(distress_rows) >= 5 else None,
        "nps": round(100 * (sum(int(row["answers"]["PU9"]) >= 9 for row in nps_rows) - sum(int(row["answers"]["PU9"]) <= 6 for row in nps_rows)) / len(nps_rows), 1) if len(nps_rows) >= 5 else None,
        "nps_respondents": len(nps_rows) if len(nps_rows) >= 5 else None,
        "reached_1wd_pct": round(100 * sum(row["answers"]["PU5"] == "yes" for row in reached_rows) / len(reached_rows), 1) if len(reached_rows) >= 5 else None,
        "reached_1wd_respondents": len(reached_rows) if len(reached_rows) >= 5 else None,
        "distress_cutoff": DISTRESS["value"],
        "synthetic": True,
    }
    has_visible_metric = any(metrics[key] is not None for key in ("informed_share_pct", "distress_at_or_above_cutoff_share_pct", "nps", "reached_1wd_pct"))
    if not has_visible_metric:
        metrics = None
    suppressed = any(count_ < 5 for count_ in (len(informed_rows), len(distress_rows), len(nps_rows), len(reached_rows)))
    return {
        "copy": {"staff": COPY[language]["staff"], "empty": COPY[language]["empty"], "open": COPY[language]["open"], "closed": COPY[language]["closed"], "close": COPY[language]["close"]},
        "tasks": tasks,
        "response_count": count,
        "open_task_count": open_count,
        "suppressed": suppressed,
        "metrics": metrics,
        "synthetic": True,
    }


@app.post("/api/feedback/{task_id}/complete")
def complete_feedback(task_id: str, payload: CompleteTask):
    if not payload.done:
        raise HTTPException(status_code=422, detail="done must be true")
    with _lock:
        for task in _tasks:
            if task["id"] == task_id:
                task["status"] = "done"
                task["completed_at"] = datetime.now(timezone.utc).isoformat()
                return {"ok": True, "task": dict(task), "synthetic": True}
    raise HTTPException(status_code=404, detail="mock follow-up task not found")



# ---- Upcoming free screening tests: plain information (sourced) and a longer check-in with a few more questions -----------------------------------
SOURCES = {
    "stm": {"label": "STM: Cancer screening", "url": "https://stm.fi/en/screening"},
    "fimlab": {"label": "Fimlab: Colorectal cancer screening", "url": "https://fimlab.fi/en/colorectal-cancer-screening/"},
    "luvn": {"label": "Western Uusimaa wellbeing county: Cancer screening", "url": "https://www.luvn.fi/en/services/health-services/health-stations/cancer-screening"},
    "relander": {"label": "Relander et al. 2025: first local results of the Finnish FIT programme", "url": "https://www.utupub.fi/items/f02dadfc-70ec-4bb2-8c9e-fe3485fb828d/full"},
}
SCREEN_COPY = {
    "fi": {
        "tab": "Tulevat ilmaiset seulonnat", "title": "Tulevat ilmaiset seulontatutkimukset",
        "lead": "Syövän seulonta on ilmaista ja vapaaehtoista. Kutsu tulee kotiin postissa.",
        "check": "Kerro, mikä auttaisi sinua osallistumaan", "mock": "Kaksi viimeistä kysymystä ovat mock-kysymyksiä: ne eivät kuulu todennettuun Pulse-kyselyyn.",
        "q3": "Mikä voisi tehdä osallistumisesta vaikeaa?", "q4": "Tiedätkö, mitä tutkimuksen jälkeen tapahtuu?",
        "sx1": "Tiesitkö, että seulontatutkimus on ilmainen?", "sx2": "Mikä auttaisi sinua eniten?",
        "o3": {"time": "Minulla ei ole aikaa", "cost": "Pelkään, että se maksaa", "language": "Kieli on este", "fear": "Pelkään tulosta", "noappt": "En saa sopivaa aikaa", "notserious": "En koe sitä tärkeäksi"},
        "o4": {"yes": "Kyllä, tiedän", "unsure": "En ole varma", "no": "En vielä"}, "o_sx1": {"yes": "Kyllä", "unsure": "En ole varma", "no": "En tiennyt"},
        "o_sx2": {"reminder": "Muistutus omalla kielelläni", "evening": "Ilta- tai viikonloppuaika", "ride": "Kyyti paikalle", "call": "Joku soittaa minulle", "nothing": "En tarvitse apua"},
        "send": "Lähetä vastaukset", "ok": "Kiitos. Vastauksesi on tallennettu tähän mock-kyselyyn.", "followup": "Kiitos. Seulontayksikkö saisi pyynnön auttaa sinua (mock).",
        "after_h": "Jos kotitesti on positiivinen", "after": "Positiivinen tulos ei tarkoita, että sinulla on syöpä, vaan että tarvitaan lisätutkimus. Ensimmäisissä paikallisissa tuloksissa noin neljä viidestä positiivisen kotitestin saaneesta kävi kolonoskopiassa. Kysy hoitajalta, jos jokin lisätutkimus huolettaa tai jos sinun on vaikea mennä.",
        "src": "Lähteet", "cost_note": "Seulontatutkimukset ovat maksuttomia (STM). Jos et ole varma jatkotutkimuksista, kysy asiaa hoitajalta.",
    },
    "sv": {
        "tab": "Kommande gratis screening", "title": "Kommande gratis screeningundersökningar",
        "lead": "Cancerscreening är gratis och frivillig. Inbjudan kommer hem med posten.",
        "check": "Berätta vad som skulle hjälpa dig att delta", "mock": "De två sista frågorna är testfrågor: de ingår inte i den validerade Pulse-enkäten.",
        "q3": "Vad skulle kunna göra det svårt att delta?", "q4": "Vet du vad som händer efter undersökningen?",
        "sx1": "Visste du att screeningundersökningen är gratis?", "sx2": "Vad skulle hjälpa dig mest?",
        "o3": {"time": "Jag har inte tid", "cost": "Jag är rädd att det kostar", "language": "Språket är ett hinder", "fear": "Jag är rädd för resultatet", "noappt": "Jag får ingen lämplig tid", "notserious": "Jag tycker inte att det är viktigt"},
        "o4": {"yes": "Ja, jag vet", "unsure": "Jag är osäker", "no": "Inte ännu"}, "o_sx1": {"yes": "Ja", "unsure": "Jag är osäker", "no": "Det visste jag inte"},
        "o_sx2": {"reminder": "Påminnelse på mitt språk", "evening": "Kväll eller helg", "ride": "Skjuts dit", "call": "Någon ringer mig", "nothing": "Jag behöver ingen hjälp"},
        "send": "Skicka svar", "ok": "Tack. Ditt svar har sparats i den här testenkäten.", "followup": "Tack. Screeningenheten skulle få en begäran om att hjälpa dig (test).",
        "after_h": "Om hemtestet är positivt", "after": "Ett positivt resultat betyder inte att du har cancer, utan att en vidare undersökning behövs. I de första lokala resultaten gick ungefär fyra av fem med positivt hemtest på koloskopi. Fråga sjuksköterskan om du är orolig för en undersökning eller har svårt att ta dig dit.",
        "src": "Källor", "cost_note": "Screeningundersökningar är kostnadsfria (STM). Om du är osäker på vidare undersökningar, fråga sjuksköterskan.",
    },
    "en": {
        "tab": "Upcoming free screening", "title": "Upcoming free screening tests",
        "lead": "Cancer screening is free of charge and voluntary. The invitation comes to your home by post.",
        "check": "Tell us what would help you take part", "mock": "The last two questions are mock questions: they are not part of the validated Pulse survey.",
        "q3": "What could make it hard to take part?", "q4": "Do you know what happens after the test?",
        "sx1": "Did you know the screening test is free?", "sx2": "What would help you most?",
        "o3": {"time": "I do not have time", "cost": "I worry it costs money", "language": "Language is a barrier", "fear": "I am afraid of the result", "noappt": "I cannot get a suitable time", "notserious": "I do not think it is important"},
        "o4": {"yes": "Yes, I know", "unsure": "I am not sure", "no": "Not yet"}, "o_sx1": {"yes": "Yes", "unsure": "I am not sure", "no": "I did not know"},
        "o_sx2": {"reminder": "A reminder in my language", "evening": "An evening or weekend time", "ride": "A ride there", "call": "Someone to call me", "nothing": "I do not need help"},
        "send": "Send answers", "ok": "Thank you. Your answers were saved in this mock survey.", "followup": "Thank you. The screening unit would get a request to help you (mock).",
        "after_h": "If the home test is positive", "after": "A positive result does not mean you have cancer; it means a further test is needed. In the first local results about four in five people with a positive home test went on to a colonoscopy. Ask your nurse if a follow-up test worries you or is hard to get to.",
        "src": "Sources", "cost_note": "Screening tests are free of charge (STM). If you are unsure about follow-up tests, ask your nurse.",
    },
}
SCREEN_INFO = {
    "fi": [
        {"id": "breast", "name": "Rintasyövän seulonta (mammografia)", "who": "Naiset, 50–69-vuotiaat", "how": "Röntgenkuvaus seulontapaikalla, kutsu noin kahden vuoden välein.", "sources": ["stm", "luvn"]},
        {"id": "crc", "name": "Suolistosyövän seulonta (kotitesti, FIT)", "who": "Kutsutaan ikäryhmittäin, laajenee vaiheittain", "how": "Otat näytteen itse kotona ja palautat sen postitse laboratorioon; kutsu noin kahden vuoden välein.", "sources": ["fimlab", "stm"]},
        {"id": "cervical", "name": "Kohdunkaulan syövän seulonta", "who": "Naiset, ikäraja vaihtelee hyvinvointialueittain: katso kutsukirjeestä", "how": "Näyte otetaan terveysasemalla, kutsu noin viiden vuoden välein.", "sources": ["stm"]},
    ],
    "sv": [
        {"id": "breast", "name": "Screening för bröstcancer (mammografi)", "who": "Kvinnor, 50–69 år", "how": "Röntgen på screeningplatsen, inbjudan ungefär vartannat år.", "sources": ["stm", "luvn"]},
        {"id": "crc", "name": "Screening för tarmcancer (hemtest, FIT)", "who": "Inbjudan efter åldersgrupp, utökas stegvis", "how": "Du tar provet själv hemma och skickar det med posten till laboratoriet; inbjudan ungefär vartannat år.", "sources": ["fimlab", "stm"]},
        {"id": "cervical", "name": "Screening för livmoderhalscancer", "who": "Kvinnor, åldersgränsen varierar mellan välfärdsområdena: se inbjudan", "how": "Provet tas på hälsostationen, inbjudan ungefär vart femte år.", "sources": ["stm"]},
    ],
    "en": [
        {"id": "breast", "name": "Breast cancer screening (mammography)", "who": "Women aged 50 to 69", "how": "An X-ray at the screening site, invitation about every two years.", "sources": ["stm", "luvn"]},
        {"id": "crc", "name": "Bowel cancer screening (home test, FIT)", "who": "Invited by age group, expanding step by step", "how": "You take the sample yourself at home and post it to the laboratory; invitation about every two years.", "sources": ["fimlab", "stm"]},
        {"id": "cervical", "name": "Cervical cancer screening", "who": "Women; the age range differs between counties: see your invitation", "how": "The sample is taken at a health station, invitation about every five years.", "sources": ["stm"]},
    ],
}


@app.get("/api/screening")
def screening_info(language: Literal["fi", "sv", "en"] = "fi"):
    """Plain information about the free screening tests (each line has its source) and the copy of the longer check-in."""
    used = {sid for p in SCREEN_INFO[language] for sid in p["sources"]} | {"relander"}
    return {"synthetic": True, "copy": SCREEN_COPY[language], "programmes": SCREEN_INFO[language],
            "sources": {sid: SOURCES[sid] for sid in used}, "moment": "screening", "items": ["PU3", "PU4", "SX1", "SX2"]}


@app.get("/logo.svg")
def logo():
    return FileResponse(ROOT / "web" / "logo.svg", media_type="image/svg+xml")

@app.get("/")
def home():
    return FileResponse(STATIC / "index.html")
