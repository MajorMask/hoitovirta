"""Sourced example journey guidance shared by My path and the voice agent."""
import json
import re
from pathlib import Path

from app import llm

FILE = Path(__file__).resolve().parents[1] / "data" / "journey_guide.json"
with FILE.open(encoding="utf-8") as f:
    GUIDE = json.load(f)
TRANSLATION_CACHE = {}
FIELDS = ("what_is_happening", "today_you_can", "ask_these", "who_to_call", "myths")
LANGUAGE_NAMES = {"sv": "Swedish", "ar": "Arabic", "so": "Somali", "ru": "Russian"}


def stage_for(store, pathway_id):
    """Map pathway events to the broad, non-clinical guide stage labels."""
    facts = store.facts(pathway_id)
    ts = facts.get("ts", {})
    if facts.get("done") or ts.get("T6"):
        return "aftercare"
    if ts.get("T5") or ts.get("T4"):
        return "decision_treatment"
    if ts.get("T3"):
        return "waiting_result"
    if ts.get("T1") or ts.get("T2"):
        return "referral_tests"
    if ts.get("T0"):
        return "suspicion"
    if ts.get("C1") or ts.get("S0") or facts.get("contacts"):
        return "first_contact"
    return "before_contact"


def _translate(stage, source, language):
    key = (stage, language)
    if key in TRANSLATION_CACHE:
        return TRANSLATION_CACHE[key], "LLM cache"
    prompt = "Translate this JSON patient-information example from English to " + LANGUAGE_NAMES[language] + ". " \
        "Preserve JSON keys, facts, advice, and links exactly; translate only text values. Do not add any medical information. " \
        "Return valid JSON only.\n" + json.dumps({k: source[k] for k in FIELDS}, ensure_ascii=False)
    translated, engine = llm.llm(prompt, system="You translate patient information faithfully. You do not add or change health advice.", max_tokens=1400)
    if not translated:
        return None, "offline"
    try:
        match = re.search(r"\{.*\}", translated, re.S)
        parsed = json.loads(match.group(0)) if match else None
        if not isinstance(parsed, dict) or any(k not in parsed for k in FIELDS):
            return None, "offline"
        TRANSLATION_CACHE[key] = parsed
        return parsed, engine
    except (TypeError, ValueError):
        return None, "offline"


def get_guide(stage, language="en"):
    if stage not in GUIDE["stages"]:
        raise KeyError(stage)
    entry = GUIDE["stages"][stage]
    lang = language if language in ("en", "fi", "sv", "ar", "so", "ru") else "en"
    translated = False
    engine = "template"
    content = entry.get(lang)
    if content is None and lang in GUIDE["translation_languages"]:
        content, engine = _translate(stage, entry["en"], lang)
        translated = content is not None
    if content is None:
        content = entry["en"]
        engine = "English fallback"
    return dict(stage=stage, language=lang if (content is not entry["en"] or lang == "en") else "en",
                **content, source_name=entry["source_name"], source_url=entry["source_url"],
                review_status=entry["review_status"],
                translation_label=GUIDE["translation_label"] if translated else ("translation unavailable; English example shown" if lang not in ("en", "fi") else ""),
                translation_engine=engine, synthetic=True)


def for_pathway(store, pathway_id, language=None):
    lang = language or store.meta[pathway_id]["language"]
    return get_guide(stage_for(store, pathway_id), lang)


def spoken_text(guide):
    lines = [guide["what_is_happening"], guide["today_you_can"], "Questions you can ask: " + " ".join(guide["ask_these"]),
             "Who to call: " + guide["who_to_call"]]
    return " ".join(lines)
