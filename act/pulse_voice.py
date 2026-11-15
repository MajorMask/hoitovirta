"""Voice answer -> Pulse field. AI converts, the patient confirms (docs/PULSE-INSTRUMENT.md rule 5): the result is always read back."""
import json
import re

from app import llm, voice
from engine.pulse import CODEBOOK

QUESTION_EN = {
    "PU1": "When did you first notice it?", "PU2": "How many times have you contacted us about this?", "PU3": "What made it hard?",
    "PU4": "Do you know what happens next?", "PU5a": "Did you try to reach your nurse?", "PU5": "Could you reach your nurse within 1 working day?", "PU6": "Were you understood in your language?",
    "PU7": "How worried have you been this week (0 to 10)?", "PU8": "How many times did you have to repeat your story?",
    "PU9": "How likely are you to recommend this care to a friend (0 to 10)?", "PU9b": "What most affected your experience?",
}
OPTION_EN = {
    "PU1": {"week": "this week", "w2_4": "2 to 4 weeks ago", "m1_3": "1 to 3 months ago", "m3p": "over 3 months ago"},
    "PU2": {"1": "once", "2": "twice", "3p": "3 or more times"},
    "PU3": {"time": "time", "cost": "cost", "language": "language", "fear": "fear", "noappt": "no appointment", "notserious": "did not seem serious"},
    "PU4": {"yes": "yes", "unsure": "not sure", "no": "no"}, "PU5a": {"yes": "yes", "no": "no", "not_tried": "I haven't tried"}, "PU5": {"yes": "yes", "no": "no"},
    "PU6": {"yes": "yes", "partly": "partly", "no": "no"}, "PU8": {"0": "never", "1": "once", "2": "twice", "3p": "3 or more times"},
}
WORDS = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
         "nolla": 0, "yksi": 1, "kaksi": 2, "kolme": 3, "neljä": 4, "viisi": 5, "kuusi": 6, "seitsemän": 7, "kahdeksan": 8, "yhdeksän": 9, "kymmenen": 10,
         "noll": 0, "ett": 1, "två": 2, "tre": 3, "fyra": 4, "fem": 5, "sex": 6, "sju": 7, "åtta": 8, "nio": 9, "tio": 10}
YESNO = {"Yes": "yes", "No": "no", "Not sure": "unsure"}


def map_answer(item, transcript, lang="en"):
    """Return dict(value, confidence, engine). value is a valid option key, or None when the speech could not be mapped."""
    kind, opts = CODEBOOK[item]
    t = (transcript or "").lower()
    if item == "PU5a" and re.search(r"haven't tried|have not tried|en ole yrittänyt|har inte försökt", t):
        return dict(value="not_tried", confidence=0.95, engine="rules")
    if kind == "scale":
        m = re.search(r"\b(10|[0-9])\b", t)
        if m:
            return dict(value=m.group(1), confidence=0.9, engine="rules")
        for w, n in WORDS.items():
            if re.search(rf"\b{w}\b", t):
                return dict(value=str(n), confidence=0.85, engine="rules")
    label = OPTION_EN.get(item, {})
    prompt = (f"A patient answered a survey question by voice. Map the answer to exactly one option key.\n"
              f"Question: {QUESTION_EN[item]}\nOptions (key: meaning): " + "; ".join(f"{k}: {label.get(k, k)}" for k in opts) +
              f"\nPatient said (language {lang}): \"{transcript}\"\n"
              'Reply ONLY with JSON: {"value": "<key>", "confidence": <0-1>}. If the answer does not clearly match an option, use confidence below 0.5.')
    raw, engine = llm.llm(prompt, max_tokens=120)
    if raw:
        try:
            j = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
            if str(j.get("value")) in opts:
                return dict(value=str(j["value"]), confidence=float(max(0, min(1, j.get("confidence", 0.5)))), engine=engine)
        except Exception:
            pass
    if item in ("PU4", "PU5", "PU5a", "PU6"):  # yes / no / not sure by keywords
        lab = voice.classify(transcript)
        v = YESNO[lab]
        if v in opts:
            return dict(value=v, confidence=0.5, engine="rules")
    return dict(value=None, confidence=0.0, engine="none")
