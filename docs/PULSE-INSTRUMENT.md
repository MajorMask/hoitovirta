# Hoitovirta Pulse: a minimal national patient data instrument

## Rules
1. **Never ask what a system already knows.** Dates of tests, stage, age band, area and language come from systems. Ask patients only what only they know.
2. **Objective first.** Dates, counts, yes/no, 0–10 scales. No open opinion questions.
3. **At most 2 core questions per moment, about 20 seconds, any language, tap or voice.** A conditional PU5 follow-up or optional, skippable PU9b comment may add one brief item.
4. **Same item codes in every county** → national comparability (FICAN/THL aggregates, cells with n < 5 suppressed).
5. **AI converts, the patient confirms.** Free speech becomes a field plus a confidence score. If unsure, it reads back once ("About 3 weeks ago?" Yes/No). AI never scores feelings: the patient gives the number.
6. **A human acts on signals.** Worry ≥ 4 triggers a coordinator call the same or next working day, never an AI conversation.

## Codebook
| Code | Asked at | Question | Answer → metric | Anchor |
|---|---|---|---|---|
| PU1 | First contact | When did you first notice it? | date → **patient interval (days)** | Aarhus statement intervals |
| PU2 | First contact | How many times have you contacted about this? | 1 / 2 / 3+ → **contacts before referral** (cross-checked with system) | multiple-consultation research |
| PU3 | Screening no-show, or PU1 > 4 weeks | What made it hard? | one tap: time · cost · language · fear · no appointment · didn't seem serious → **barrier mix by area and language** | equity gap |
| PU4 | Suspicion told, each handover | Do you know what happens next? | yes / not sure / no → **% informed** | Hoitovirta Experience Index |
| PU5a | Each handover | Did you try to reach your nurse? | yes / no / I haven't tried → routes the conditional follow-up | Hoitovirta process measure |
| PU5 | Each handover, only if PU5a = yes | Could you reach your nurse within 1 working day? | yes / no → **% reached within 1 working day** | coordinator standard |
| PU6 | First contact (if not Finnish/Swedish) | Were you understood in your language? | yes / partly / no → **language gap** | equity |
| PU7 | Suspicion, diagnosis | How worried have you been this week? | 0–10 → **distress ≥ 4 share**; triggers a call | NCCN Distress Thermometer (validated, cutoff ≥ 4) |
| PU8 | Treatment start | How many times did you repeat your story? | 0 / 1 / 2 / 3+ → **continuity** | |
| PU9 | Diagnosis, treatment start (asked first) | How likely to recommend this care? | 0–10 → **NPS** | roadmap 1.2.2 (NPS > 80) |
| PU9b | Optional after PU9 at diagnosis or treatment start | What most affected your experience? | optional free text or voice transcription; skip allowed | Hoitovirta qualitative follow-up |
| PU10 | Aftercare, monthly | EQ-5D-5L (5 taps) | → **quality of life** | roadmap 3.3 outcomes |

## Schedule (≤ 2 per moment)
First contact: PU1 + PU2 (+PU6) · Suspicion: PU4 + PU7 · Each handover: PU4 + PU5a, then PU5 only if PU5a = yes · Diagnosis: PU9 first, then PU7, then optional PU9b · Treatment start: PU9 first, then PU8, then optional PU9b · Aftercare: PU10 monthly · Screening no-show: PU3.

## Channels (easiest first)
SMS link (one tap) · phone voice (read aloud, answer by voice or keypad) · app · lobby kiosk (offline) · nurse asks during a call (counts as data entry).

## Data
`response(pathway_id pseudonymous, moment, item_code, value, unit, language, channel, ts, ai_confidence, entered_by=patient|staff)` → FHIR QuestionnaireResponse → county dashboard → national aggregates.

## What it unlocks
Patient interval + system diagnostic interval = **the full first-symptom → diagnosis clock**, by area, language and cancer. It's measured nowhere in Finland today.
Also: who is left behind and why (barriers), calm (distress, % informed), continuity, NPS, and the share who reached a nurse within 1 working day among patients who tried.

## Sources
- NCCN Distress Thermometer, cutoff ≥ 4: https://pmc.ncbi.nlm.nih.gov/articles/PMC7587428 ; https://pmc.ncbi.nlm.nih.gov/articles/PMC6750919
