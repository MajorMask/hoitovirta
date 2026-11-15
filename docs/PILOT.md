# One county, twelve months: pilot proposal

This is a proposal, not a result. Everything patient-level in the prototype is synthetic.

## Where and why

**Länsi-Uusimaa.** It had one of the three lowest screening participation rates in 2024, together with Helsinki and Vantaa–Kerava (Finnish Cancer Registry), and it is the county where the prototype's coordinator and patients are set. A county that already feels the gap is a fair place to prove a fix.

## What changes for the people involved

1. **A nurse taps once** when a suspected cancer is recorded. The clock starts and a coordinator is named.
2. **A coordinator owns the waiting.** One ranked list of who to call, the open loops nobody owns, and a message in the patient's language that she approves.
3. **The patient knows what happens next.** Next step, date and named nurse in their own language, and two short questions that ask the nurse to call when worry is high.

## What we measure

| Measure | Why it matters | Target |
|---|---|---|
| Median days from first contact to diagnosis (headline) | Measured nowhere in Finland today | Pilot goal below |
| Gap in that median between language groups | The equal-care test | No group more than 7 days above the county median (our assumption) |
| Coordinator named within one working day | Someone owns the waiting | 100% (our assumption) |
| Open loops older than seven days | Nothing falls between steps | None |
| Patients who say they knew what happens next | The patient's own view | Higher than baseline; the target comes from the baseline |
| Patients who reached a nurse within one working day | Reachability | Higher than baseline |

## The pilot goal

Cut the lung-cancer wait by about 45 days, which is roughly half of the 88-day gap between Finland (155 days) and Denmark (67 days, preliminary study, Yle MOT, Oct 2026). This is our goal, not a forecast. The first three months set the real baseline; the target is then reset against it.

## What a county has to provide

- A timestamped export of contacts, referrals, tests and diagnoses (CSV or FHIR), mapped with the adapters in `ingest/`.
- Clinicians to review the red-flag list and procedures before real use. The ones in the prototype are examples.
- A data protection impact assessment and a named data owner.
- Native readers to check the Finnish, Swedish, Arabic, Russian and Somali texts.

## What we are not claiming

That any score is validated, that the product is certified, or that the time saved is proven. The evidence behind each number, and its status, is in [EVIDENCE.md](EVIDENCE.md).
