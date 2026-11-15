"""Shared, language-aware emergency phrases and patient-facing safety text.

This is emergency safety-netting for the prototype, not a clinical red-flag
classifier. It must never start T0 or make a diagnosis.
"""
import re

URGENT_TERMS = {
    "en": ("chest pain", "can't breathe", "cannot breathe", "trouble breathing", "difficulty breathing",
           "heavy bleeding", "sudden weakness", "sudden confusion", "confusion", "suicid", "kill myself", "end my life", "hurt myself"),
    "fi": ("rintakipu", "hengitysvaikeus", "en pysty hengittämään", "runsas verenvuoto", "äkillinen heikkous",
           "äkillinen sekavuus", "itsemurha", "vahingoittaa itseäni"),
    "sv": ("bröstsmärta", "svårt att andas", "kan inte andas", "andningssvårigheter", "kraftig blödning",
           "plötslig svaghet", "plötslig förvirring", "självmord", "skada mig själv"),
    "ar": ("ألم في الصدر", "صعوبة في التنفس", "لا أستطيع التنفس", "نزيف شديد", "ضعف مفاجئ", "ارتباك مفاجئ", "أريد الانتحار", "أؤذي نفسي"),
    "ru": ("боль в груди", "трудно дышать", "не могу дышать", "сильное кровотечение", "внезапная слабость",
           "внезапная спутанность", "самоубийство", "причинить себе вред"),
}
SELF_HARM_TERMS = {
    "en": ("suicid", "kill myself", "end my life", "hurt myself"),
    "fi": ("itsemurha", "vahingoittaa itseäni"),
    "sv": ("självmord", "skada mig själv"),
    "ar": ("أريد الانتحار", "أؤذي نفسي"),
    "ru": ("самоубийство", "причинить себе вред"),
}
URGENT_REPLY = {
    "en": "This may be an emergency. Call 112 now. I can ask your nurse to call you today.",
    "fi": "Tämä voi olla hätätilanne. Soita heti numeroon 112. Voin pyytää hoitajaa soittamaan tänään.",
    "sv": "Det här kan vara akut. Ring 112 nu. Jag kan be sjuksköterskan ringa dig i dag.",
    "ar": "قد تكون هذه حالة طارئة. اتصل بالرقم 112 الآن. يمكنني أن أطلب من الممرضة الاتصال بك اليوم.",
    "ru": "Это может быть неотложная ситуация. Позвоните по номеру 112 сейчас. Я могу попросить медсестру позвонить вам сегодня.",
}
SELF_HARM_REPLY = {
    "en": "I am sorry this feels difficult. If you may hurt yourself, call 112 now. I can ask your nurse to call you today.",
    "fi": "Olen pahoillani, että sinulla on vaikeaa. Jos saatat vahingoittaa itseäsi, soita heti 112. Voin pyytää hoitajaa soittamaan tänään.",
    "sv": "Jag är ledsen att det känns svårt. Om du riskerar att skada dig själv, ring 112 nu. Jag kan be sjuksköterskan ringa i dag.",
    "ar": "أنا آسف لأنك تمر بوقت صعب. إذا كنت قد تؤذي نفسك، اتصل بالرقم 112 الآن. يمكنني أن أطلب من الممرضة الاتصال بك اليوم.",
    "ru": "Мне жаль, что вам сейчас трудно. Если вы можете причинить себе вред, позвоните по номеру 112 сейчас. Я могу попросить медсестру позвонить вам сегодня.",
}


def _has_any(text, terms):
    normalized = re.sub(r"\s+", " ", str(text or "").casefold())
    return any(term.casefold() in normalized for values in terms.values() for term in values)


def is_urgent(text):
    return _has_any(text, URGENT_TERMS)


def is_self_harm(text):
    return _has_any(text, SELF_HARM_TERMS)


def patient_message(language="en", *, self_harm=False):
    messages = SELF_HARM_REPLY if self_harm else URGENT_REPLY
    return messages.get(language, messages["en"])
