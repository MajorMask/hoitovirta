"""Domain constants shared by engine, sim, act and api. Clinical content comes from the pathway notes.
Red-flag chips are examples to be validated with clinicians before any real use. All cohorts are synthetic."""
from datetime import datetime, timedelta, timezone

STEPS = ["T0", "T1", "T2", "T3", "T4", "T5", "T6"]
CANCERS = ["lung", "breast", "colorectal", "prostate", "haematological"]
CANCER_LABEL = {"lung": "Lung", "breast": "Breast", "colorectal": "Colorectal", "prostate": "Prostate", "haematological": "Haematological"}

STEP_LABEL = {"T0": "Suspicion", "T1": "Referral sent", "T2": "Referral received", "T3": "First test",
              "T4": "Diagnosis", "T5": "MDT", "T6": "Treatment"}
TEST_NAME = {"lung": "CT scan", "breast": "Recall imaging", "colorectal": "Colonoscopy", "prostate": "MRI", "haematological": "SPEP + FLC blood test"}


def step_name(cancer, step):
    return TEST_NAME[cancer] if step == "T3" else STEP_LABEL[step]


# Red flags per cancer (the pathway notes "Main door" and "Safety-net rule")
RED_FLAGS = {
    "lung": ["Cough over 3 weeks", "Coughing blood", "Weight loss", "Nodule on X-ray or CT"],
    "breast": ["Breast lump", "Abnormal mammogram"],
    "colorectal": ["Positive FIT", "Rectal bleeding", "Change in bowel habit"],
    "prostate": ["Raised PSA", "Urinary symptoms"],
    "haematological": ["Back or bone pain, 3rd visit", "Fatigue and infections", "Abnormal blood count"],
}
FLAG_CANCER = {f: c for c, fl in RED_FLAGS.items() for f in fl}

# Reason shown on the worklist when a step is finished and nothing is booked next (the pathway notes safety-net rules)
LOOP_REASON = {
    ("lung", "pre"): "Nodule or red flag, no CT booked",
    ("breast", "pre"): "Abnormal screen, no assessment booked",
    ("colorectal", "pre"): "Positive FIT, no colonoscopy booked",
    ("prostate", "pre"): "Raised PSA, no MRI booked",
    ("haematological", "pre"): "3rd contact, no SPEP + FLC booked",
    ("lung", "T3"): "CT done, no biopsy booked",
    ("breast", "T3"): "Imaging done, no biopsy booked",
    ("colorectal", "T3"): "Colonoscopy done, no biopsy result booked",
    ("prostate", "T3"): "MRI done, no biopsy booked",
    ("haematological", "T3"): "Blood test done, no haematology visit booked",
    ("any", "T4"): "Diagnosis made, no MDT booked",
    ("any", "T5"): "MDT done, no treatment booked",
}
FLAG_REASON = {"Positive FIT": "Positive FIT, no colonoscopy booked", "Nodule on X-ray or CT": "Nodule, no CT booked",
               "Back or bone pain, 3rd visit": "3rd contact with back pain, no SPEP + FLC booked"}

LANGUAGES = {"fi": "Finnish", "sv": "Swedish", "ar": "Arabic", "so": "Somali", "ru": "Russian", "en": "English"}
DOMESTIC = {"fi", "sv"}

COUNTIES = ["Länsi-Uusimaa", "Helsinki", "Vantaa–Kerava", "Pirkanmaa", "Lappi"]
COORDINATORS = {
    "Länsi-Uusimaa": ["Laura", "Mikko", "Aisha"],
    "Helsinki": ["Petra", "Omar", "Elina"],
    "Vantaa–Kerava": ["Sanna", "Jussi", "Fatima"],
    "Pirkanmaa": ["Heidi", "Antti", "Noora"],
    "Lappi": ["Anne", "Tuomas", "Saara"],
}

UTC = timezone.utc


def parse_ts(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def fmt_ts(d):
    return d.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def days_between(a, b):
    return (b - a).total_seconds() / 86400.0


def add_days(d, n):
    return d + timedelta(days=n)

FULLNAME = {"Laura": "Laura Niemi", "Mikko": "Mikko Laine", "Aisha": "Aisha Rahman", "Petra": "Petra Virtanen", "Omar": "Omar Haddad", "Elina": "Elina Korhonen",
            "Sanna": "Sanna Mäkelä", "Jussi": "Jussi Heikkinen", "Fatima": "Fatima Ali", "Heidi": "Heidi Koskinen", "Antti": "Antti Lehtonen", "Noora": "Noora Salminen",
            "Anne": "Anne Lindholm", "Tuomas": "Tuomas Aalto", "Saara": "Saara Rantanen"}
PLACES = {"Länsi-Uusimaa": "Jorvi hospital", "Helsinki": "Meilahti hospital", "Vantaa–Kerava": "Peijas hospital",
          "Pirkanmaa": "Tampere University Hospital", "Lappi": "Lapland Central Hospital"}
