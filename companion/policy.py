"""Reviewable policy constants and deterministic guardrails for the patient companion."""
import re

ALLOWED_INTENTS = {
    "where_am_i", "prepare", "wait_worry", "glossary", "practical",
    "feelings", "family", "call_person", "out_of_scope",
}
NEEDS = {"info_gap", "transport", "interpreter", "schedule_conflict", "practical_cost",
         "caregiver_support", "fear_or_distress", "other"}
ESCALATIONS = {"none", "ask_coordinator", "callback_today", "emergency"}
BUTTONS = {"call_nurse", "ask_coordinator", "book_interpreter"}

# The model receives this blocklist and the caller is also screened against its prompt-injection rules.
BLOCKED_CLAIMS = (
    re.compile(r"\b(?:you (?:do not|don't) have cancer|you have cancer|it is cancer|it's cancer|cancer[- ]free|benign|malignant)\b", re.I),
    re.compile(r"\b(?:survival rate|life expectancy|months? to live|years? to live|you will (?:recover|die|survive))\b", re.I),
    re.compile(r"\b(?:don't worry|do not worry|everything will be fine|it will be fine|you'll be fine)\b", re.I),
    re.compile(r"\b(?:take|stop|start|change|increase|decrease)\s+(?:the\s+)?(?:medicine|medication|drug|tablet|pill|dose)\b", re.I),
    re.compile(r"\b(?:do not|don't)\s+(?:eat|drink|take)\b", re.I),
    re.compile(r"\b(?:take|use)\s+\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|mL|units?)\b", re.I),
)
OUT_OF_SCOPE = (
    re.compile(r"\b(?:is this cancer|do i have cancer|what stage (?:is it|am i)|stage of (?:my|the) cancer)\b", re.I),
    re.compile(r"\b(?:what dose|how much .* should i take|should i take .* medication|treatment choice|which treatment)\b", re.I),
    re.compile(r"\b(?:survival rate|am i going to die|how long .* live|second opinion)\b", re.I),
    re.compile(r"\b(?:legal advice|sue the hospital|financial advice|unrelated|write (?:me )?a poem|translate this essay)\b", re.I),
)
INJECTION = (
    re.compile(r"\bignore (?:all )?(?:previous|prior|your) (?:instructions|rules|prompt)\b", re.I),
    re.compile(r"\b(?:role[- ]?play|act as|pretend you are|reveal your system prompt|developer message)\b", re.I),
    re.compile(r"\b(?:write|compose) (?:me )?(?:a )?(?:poem|essay|story|joke)\b", re.I),
)
EMERGENCY = (
    re.compile(r"\bchest pain\b", re.I),
    re.compile(r"\b(?:cannot|can't|unable to) breathe\b|\btrouble breathing\b|\bshortness of breath\b", re.I),
    re.compile(r"\b(?:heavy|severe|uncontrolled) bleeding\b|\bbleeding a lot\b", re.I),
    re.compile(r"\b(?:sudden weakness|suddenly weak|face droop|one side weakness)\b", re.I),
    re.compile(r"\b(?:sudden )?confusion\b", re.I),
    re.compile(r"\b(?:suicid(?:e|al)|end my life|kill myself|hurt myself|self[- ]harm)\b", re.I),
    # Common Finnish / Swedish / Arabic / Russian emergency phrases used in this synthetic product.
    re.compile(r"\b(?:rintakipu|voimakas verenvuoto|hengitysvaikeus|itsemurha|tajunnan menetys)\b", re.I),
    re.compile(r"\b(?:bröstsmärta|svårt att andas|kraftig blödning|självmord|plötslig svaghet)\b", re.I),
    re.compile(r"(?:ألم في الصدر|لا أستطيع التنفس|صعوبة في التنفس|نزيف شديد|انتحار|боль в груди|не могу дышать|сильное кровотечение|суицид)"),
)
FAMILY_PRIVATE = re.compile(r"\b(?:biopsy|pathology|test result|what did .* show|diagnosis|stage|cancer)\b", re.I)

REDIRECT = {
    "en": "That is a question for your doctor or nurse. I can ask the coordinator to call you about it. Do you want that?",
    "fi": "Tuo on kysymys lääkärille tai hoitajalle. Voin pyytää koordinaattoria soittamaan sinulle. Haluatko sitä?",
    "sv": "Det är en fråga för din läkare eller sjuksköterska. Jag kan be samordnaren ringa dig. Vill du det?",
}
FAMILY_PRIVATE_TEXT = {
    "en": "That information is not shared in the family view. Please ask the patient or their nurse.",
    "fi": "Tätä tietoa ei näytetä läheisnäkymässä. Kysy potilaalta tai hänen hoitajaltaan.",
    "sv": "Den informationen visas inte i närståendens vy. Fråga patienten eller hens sjuksköterska.",
}
EMERGENCY_TEXT = {
    "en": "This may be an emergency. Call 112 now. I can also ask your nurse to call you today.",
    "fi": "Tämä voi olla hätätilanne. Soita heti numeroon 112. Voin myös pyytää hoitajaa soittamaan sinulle tänään.",
    "sv": "Det här kan vara akut. Ring 112 nu. Jag kan också be sjuksköterskan ringa dig i dag.",
}
SELF_HARM_TEXT = {
    "en": "I am sorry this feels so hard. If you may hurt yourself, call 112 now or go to emergency care. I can ask your nurse to call you today.",
    "fi": "Olen pahoillani, että sinulla on näin vaikeaa. Jos saatat vahingoittaa itseäsi, soita heti 112 tai hakeudu päivystykseen. Voin pyytää hoitajaa soittamaan tänään.",
    "sv": "Jag är ledsen att det känns så svårt. Om du riskerar att skada dig själv, ring 112 nu eller sök akut vård. Jag kan be sjuksköterskan ringa dig i dag.",
}
SAFE_FALLBACK = {
    "en": "I am not sure. I can ask the coordinator to contact you. Would you like that?",
    "fi": "En ole varma. Voin pyytää koordinaattoria ottamaan sinuun yhteyttä. Haluatko sitä?",
    "sv": "Jag är inte säker. Jag kan be samordnaren kontakta dig. Vill du det?",
}


def language_key(language):
    return language if language in ("fi", "sv", "en") else "en"


def emergency_kind(text):
    if any(re.search(r"\b(?:suicid(?:e|al)|end my life|kill myself|hurt myself|self[- ]harm)\b|itsemurha|självmord|انتحار|суицид", text or "", re.I)
           for _ in (0,)):
        return "self_harm"
    return "emergency" if any(p.search(text or "") for p in EMERGENCY) else None


def redirect(language):
    return REDIRECT.get(language_key(language), REDIRECT["en"])


def emergency_reply(language, kind):
    table = SELF_HARM_TEXT if kind == "self_harm" else EMERGENCY_TEXT
    return table.get(language_key(language), table["en"])


def is_blocked_claim(text):
    return any(p.search(text or "") for p in BLOCKED_CLAIMS)


def out_of_scope(text):
    return any(p.search(text or "") for p in OUT_OF_SCOPE)


def injection(text):
    return any(p.search(text or "") for p in INJECTION)
