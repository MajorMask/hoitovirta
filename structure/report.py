"""Report structuring: free report text -> event fields with a confidence score. Below 0.7 goes to the "needs check" queue.
The model extracts; a person confirms. A cross-check with simple rules lowers confidence when they disagree, so a doubtful
extraction is never saved silently. Suspicious finding with no next step stated is flagged for the coordinator.
The AI never decides clinically: diagnosis and stage are only ever written after a person confirms them."""
import json
import re

from app import llm

NEEDS_CHECK = 0.7
KINDS = ("imaging", "lab", "pathology", "other")
STAGES = ("I", "II", "III", "IV", "unknown")
PROMPT = ("Extract fields from this radiology, laboratory or pathology report. Reply with ONLY compact JSON with keys: "
          '"kind" (one of imaging, lab, pathology, other), "test" (string, the test name), "finding" (string, max 14 words), '
          '"suspicious" (true if the report describes a finding suspicious for cancer, else false), '
          '"next_step_stated" (true if the report itself recommends a next step), "next_step" (string or null), '
          '"stage" (I, II, III, IV or unknown: only if the report states a stage), '
          '"confidence" (number 0-1: how sure you are the fields are right). Do not diagnose or advise. Report:\n\n')
SUSPICIOUS = re.compile(r"suspicious|malignan|carcinoma|spiculat|lymphadenopathy|\bmass\b|raised|elevated|M-spike|ratio", re.I)
BENIGN = re.compile(r"\bno (suspicious|evidence of|abnormal)|within normal limits|unremarkable|benign", re.I)
NEXT = re.compile(r"recommend|follow[- ]?up|refer|biopsy|MDT|repeat|further imaging|PET|correlat", re.I)
STAGE = re.compile(r"stage\s*(IV|III|II|I)\b", re.I)
KIND_WORDS = [("pathology", r"biops|histolog|cytolog|carcinoma|specimen"), ("imaging", r"\bCT\b|MRI|x-?ray|radiograph|ultrasound|mammogra|PET"),
              ("lab", r"blood|SPEP|FLC|light chain|PSA|FIT|haemoglobin|count|serum")]


def rules_view(text):
    """Independent, simple reading of the same text, used only to cross-check the model."""
    sus = bool(SUSPICIOUS.search(text)) and not (BENIGN.search(text) and not re.search(r"suspicious for|malignan|carcinoma", text, re.I))
    kind = next((k for k, pat in KIND_WORDS if re.search(pat, text, re.I)), "other")
    m = STAGE.search(text)
    return dict(kind=kind, suspicious=sus, next_step_stated=bool(NEXT.search(text)), stage=m.group(1).upper() if m else "unknown")


def structure(text):
    rules = rules_view(text)
    out, engine = None, "offline rules"
    raw, eng = llm.llm(PROMPT + text[:4000], max_tokens=350)
    if raw:
        try:
            out = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))
            engine = eng
        except Exception:
            out = None
    if out is None:
        out = dict(kind=rules["kind"], test="unknown", finding=text.strip().split(".")[0][:80], suspicious=rules["suspicious"],
                   next_step_stated=rules["next_step_stated"], next_step=None, stage=rules["stage"], confidence=0.5)
    out["kind"] = out.get("kind") if out.get("kind") in KINDS else rules["kind"]
    out["stage"] = str(out.get("stage", "unknown")).upper() if str(out.get("stage", "unknown")).upper() in STAGES else "unknown"
    out["suspicious"], out["next_step_stated"] = bool(out.get("suspicious")), bool(out.get("next_step_stated"))
    conf = float(max(0.0, min(1.0, out.get("confidence", 0.5))))
    # cross-check: if the model and the rules disagree on a safety-critical field, do not trust the high confidence
    agree = dict(suspicious=out["suspicious"] == rules["suspicious"], next_step=out["next_step_stated"] == rules["next_step_stated"],
                 stage=(out["stage"] == rules["stage"]) or rules["stage"] == "unknown")
    if not agree["suspicious"] or not agree["next_step"]:
        conf = min(conf, 0.6)
    out["confidence"] = round(conf, 2)
    out["agreement"] = agree
    out["needs_check"] = conf < NEEDS_CHECK
    out["open_loop_flag"] = out["suspicious"] and not out["next_step_stated"]
    out["engine"] = engine
    return out
