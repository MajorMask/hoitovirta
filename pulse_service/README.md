# Hoitovirta Pulse sidecar

A separate FastAPI service for an isolated patient feedback survey and a mock care-team follow-up queue. It is not mounted in `api/main.py`, imports no main-app event store, and the current `web/` application has no dependency on it. A future interface can consume its JSON API or embed the standalone page after review.

## Run locally

From the repository root:

```sh
uvicorn pulse_service.main:app --host 127.0.0.1 --port 8011
```

Open `http://127.0.0.1:8011/`. The page is a Finnish-first suspicion-moment survey with Swedish and English options, and a switch to the separate mock care-team queue. All cases and outputs are synthetic. Responses and tasks are held in process memory and disappear when the service stops. Do not use real patient identifiers or health information.

## Survey and feedback

The API exposes the canonical Pulse moments and item keys from `docs/PULSE-INSTRUMENT.md` and `engine/pulse.py`:

- First contact: PU1 + PU2 (PU6 can replace PU2 when language access is asked).
- Suspicion: PU4 + PU7.
- Handover: PU4 + PU5a; PU5 is required only when PU5a is `yes`. `not_tried` is valid.
- Diagnosis: PU9 + PU7; optional, skippable PU9b.
- Treatment: PU9 + PU8; optional, skippable PU9b.

The patient gives the answer; this service does not estimate, diagnose, score symptoms, or call a model. A PU7 answer at the sourced threshold creates a **mock** nurse follow-up task. PU4 unsure/no and PU5 no create mock clarification/contact tasks. No real message, call, clinical action, or T0 event is created. The task due timing follows the Pulse rule in `docs/PULSE-INSTRUMENT.md`.

Aggregates use separate denominators per item, and each measure is hidden until it has at least five answers. The distress cutoff and source URL load from `data/evidence.json`; the instrument response also cites `docs/PULSE-INSTRUMENT.md` and `the process playbook`. The distress cutoff is not a diagnosis or automatic clinical decision.

## API contract

- `GET /health`
- `GET /api/instrument?language=fi|sv|en` — item catalog, moment schedule, synthetic label, cutoff, and source references.
- `POST /api/responses` — accepts only `DEMO-*` cases; `moment`, `language`, `channel`, and an `answers` map. Returns saved synthetic answers and any mock follow-up signal.
- `GET /api/feedback?language=fi|sv|en` — mock tasks and server-suppressed aggregates.
- `POST /api/feedback/{task_id}/complete` — marks a mock task complete.

The first static page still submits the original flat PU4/PU7 payload for compatibility; the service accepts that shape as well as the documented `answers` map.

## Assumptions / limits

- The service uses in-memory mock storage, not production persistence or authentication.
- `DEMO-*` validation is a demonstration guard, not an identity or access-control system.
- No browser or assistive-technology audit has been completed. Unit and endpoint tests are in `tests/test_pulse_service.py`.
- There is no symptom triage or emergency detector here. If integrated into a patient product, show the county's official contact route and clinically reviewed safety instructions; do not infer urgency from free text.
