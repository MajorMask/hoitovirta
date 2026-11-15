"""Synthetic people and incoming calls. Names are invented and not linked to real patients."""
import random

from engine.domain import DOMESTIC, FLAG_CANCER, RED_FLAGS

NAMES = {  # language -> (female, male) first names
    "fi": (["Sari", "Liisa", "Anna", "Helena", "Marjatta", "Tuula", "Päivi", "Riitta"], ["Matti", "Juha", "Pekka", "Timo", "Kari", "Eero", "Antti", "Hannu"]),
    "sv": (["Karin", "Ingrid", "Maria", "Britt", "Eva"], ["Lars", "Erik", "Johan", "Anders", "Bo"]),
    "ar": (["Amina", "Fatima", "Layla", "Mariam", "Noor"], ["Omar", "Yusuf", "Hassan", "Ahmed", "Khaled"]),
    "so": (["Hodan", "Faduma", "Ayaan", "Sahra"], ["Abdi", "Mohamed", "Ali", "Ismail"]),
    "ru": (["Olga", "Irina", "Natalia", "Svetlana"], ["Sergey", "Dmitri", "Vladimir", "Andrei"]),
    "en": (["Sara", "Emma", "Priya", "Grace"], ["John", "David", "Mark", "Paul"]),
}
LANG_MIX = {  # synthetic language mix by county
    "Länsi-Uusimaa": {"fi": .62, "sv": .10, "ar": .07, "so": .04, "ru": .07, "en": .10},
    "Helsinki": {"fi": .55, "sv": .06, "ar": .08, "so": .06, "ru": .12, "en": .13},
    "Vantaa–Kerava": {"fi": .58, "sv": .03, "ar": .09, "so": .07, "ru": .13, "en": .10},
    "Pirkanmaa": {"fi": .90, "sv": .01, "ar": .02, "so": .02, "ru": .03, "en": .02},
    "Lappi": {"fi": .93, "sv": .01, "ar": .01, "so": .01, "ru": .02, "en": .02},
}
CANCER_MIX = {"lung": .25, "breast": .25, "colorectal": .25, "prostate": .15, "haematological": .10}
AGE = {"lung": (55, 82), "breast": (45, 74), "colorectal": (56, 76), "prostate": (55, 79), "haematological": (45, 85)}
FLAG_W = {"Positive FIT": 6, "Rectal bleeding": 3, "Change in bowel habit": 1, "Cough over 3 weeks": 4, "Coughing blood": 2, "Weight loss": 3,
          "Nodule on X-ray or CT": 3, "Breast lump": 5, "Abnormal mammogram": 5, "Raised PSA": 7, "Urinary symptoms": 3,
          "Back or bone pain, 3rd visit": 4, "Fatigue and infections": 3, "Abnormal blood count": 3}
SAYS = {"Positive FIT": "home test came back positive", "Rectal bleeding": "blood when going to the toilet", "Change in bowel habit": "bowel habit changed for weeks",
        "Cough over 3 weeks": "cough that will not go away", "Coughing blood": "coughed up blood", "Weight loss": "losing weight without trying",
        "Nodule on X-ray or CT": "spot seen on a chest X-ray", "Breast lump": "found a lump", "Abnormal mammogram": "recalled after mammogram",
        "Raised PSA": "PSA test was high", "Urinary symptoms": "trouble passing urine",
        "Back or bone pain, 3rd visit": "back pain, has called before", "Fatigue and infections": "tired and keeps getting infections",
        "Abnormal blood count": "blood test looked abnormal"}


def pick(r, weights):
    return r.choices(list(weights), weights=list(weights.values()))[0]


def person(r, county, cancer=None, language=None):
    cancer = cancer or pick(r, CANCER_MIX)
    language = language or pick(r, LANG_MIX[county])
    sex = "f" if cancer == "breast" else ("m" if cancer == "prostate" else r.choice("fm"))
    first = r.choice(NAMES[language][0 if sex == "f" else 1])
    lo, hi = AGE[cancer]
    age = r.randint(lo, hi)
    return dict(name=f"{first} {r.choice('ABEHJKLMNPRSTVW')}.", age=age, sex=sex, language=language, cancer=cancer,
                interpreter=language not in DOMESTIC and r.random() < 0.7,
                g8=(r.randint(8, 17) if age >= 65 else None))


def make_call(r, county, call_id):
    cancer = pick(r, CANCER_MIX)
    p = person(r, county, cancer)
    flag = r.choices(RED_FLAGS[cancer], weights=[FLAG_W[x] for x in RED_FLAGS[cancer]])[0]
    prior = []
    if r.random() < 0.45 or flag.startswith("Back or bone"):
        n = 2 if (flag.startswith("Back or bone") or r.random() < 0.5) else 1
        d = r.randint(20, 40)
        for _ in range(n):
            prior.append(dict(days_ago=d, kind=r.choice(["phone", "eVisit", "phone"]), symptom=SAYS[flag]))
            d = max(d - r.randint(8, 16), 2)
    return dict(id=call_id, county=county, name=p["name"], age=p["age"], sex=p["sex"], language=p["language"], interpreter=p["interpreter"],
                g8=p["g8"], says=SAYS[flag], suggested_flag=flag, prior=prior, cancer=cancer)
