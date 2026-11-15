-- Hoitovirta Pathway Event Standard v1.0 (aggregate-ready, county-adoptable). PostgreSQL (Aiven) and SQLite compatible.
-- One append-only EVENT table is the single source of truth. Pathway state, intervals and KPIs are DERIVED, never typed.
-- Replaces v0.1 (one row per pathway episode, kept in archive/schema-v0.1-pathway-episode.sql).
-- Contains NO direct identifiers: pathway ids are pseudonymous and county-internal; only aggregates leave the county (cells n < 5 suppressed).
-- ALL DATA IN THIS REPOSITORY IS SYNTHETIC.

CREATE TABLE IF NOT EXISTS pathways (
  id          TEXT PRIMARY KEY,           -- pseudonymous pathway id
  name        TEXT,                       -- display name (synthetic); a county would keep this in its own system
  age         INTEGER,
  sex         TEXT,                       -- 'f' | 'm'
  language    TEXT,                       -- fi sv ar so ru en (equity analysis; interpreter flag below)
  county      TEXT,                       -- wellbeing services county (hyvinvointialue)
  cancer      TEXT,                       -- lung breast colorectal prostate haematological
  onset_days  INTEGER,                    -- patient interval, from Pulse PU1 (days from first symptom to first contact)
  interpreter INTEGER                     -- 0/1
);

CREATE TABLE IF NOT EXISTS events (
  id          BIGINT PRIMARY KEY,
  pathway_id  TEXT NOT NULL REFERENCES pathways(id),
  ts          TEXT NOT NULL,              -- UTC, 'YYYY-MM-DDTHH:MM:SSZ'
  type        TEXT NOT NULL,              -- see the catalogue below
  value       TEXT,                       -- text, number or JSON for structured events
  unit        TEXT,                       -- e.g. 'flag', 'score', 'call-out', Pulse moment
  source      TEXT,                       -- triage | ehr | pulse:sms | report:<engine> | engine:<rule> | ingest:ehr-csv | ingest:fhir | coordinator ...
  confidence  REAL,                       -- 0..1 for AI-structured fields; below 0.7 goes to the "needs check" queue
  entered_by  TEXT                        -- nurse:<n> | coordinator:<n> | patient | system | engine | diagnostics:<n> | ingest
);
CREATE INDEX IF NOT EXISTS events_pathway ON events (pathway_id);
CREATE INDEX IF NOT EXISTS events_type ON events (type);

-- Voice service operational records use the same DB connection and SQLite fallback as pathway events.
CREATE TABLE IF NOT EXISTS voice_call (
  conversation_id TEXT PRIMARY KEY, ts TEXT NOT NULL, caller_type TEXT, language TEXT,
  summary TEXT, review_needed INTEGER NOT NULL DEFAULT 0, raw TEXT
);
CREATE TABLE IF NOT EXISTS task (
  id TEXT PRIMARY KEY, pathway_id TEXT, ts TEXT NOT NULL, kind TEXT NOT NULL,
  detail TEXT, done INTEGER NOT NULL DEFAULT 0, assigned_to TEXT
);
CREATE INDEX IF NOT EXISTS task_assigned ON task (assigned_to, done, ts);
CREATE TABLE IF NOT EXISTS access_log (
  id TEXT PRIMARY KEY, ts TEXT NOT NULL, staff_id TEXT, role TEXT, action TEXT,
  ok INTEGER NOT NULL, pathway_id TEXT
);

-- Event catalogue
--   T0  point of suspicion (red flag tapped, or first recorded suspicion)          value = red flag
--   T1  referral sent        T2 referral received       T3 first diagnostic test   T4 diagnosis
--   T5  MDT decision         T6 first treatment
--   stage (I..IV | unknown)  g8 (score, age >= 65)      coordinator (name)         handover {from,to,note}
--   contact (earlier contact; unit = phone|eVisit|question|call-out)  booking {step,due,by,slot}  message {text,language,engine,...}
--   slip {step,why}          open_loop {state: open|closed, reason, rule}           report {report_id,status,fields,...}
--   pulse:PU1..PU10  (one event per answer; unit = moment)
-- Derived, never stored: S0 symptom onset = T0 - onset_days (Pulse PU1);  C1 first contact = earliest 'contact' event, else T0.

-- Screening and outreach (SYNTHETIC invites; person-level lists stay in the screening unit)
CREATE TABLE IF NOT EXISTS screening_invites (id TEXT PRIMARY KEY, county TEXT, programme TEXT, name TEXT, age INTEGER, language TEXT, invited_ts TEXT);
CREATE TABLE IF NOT EXISTS outreach_events (id BIGINT PRIMARY KEY, ts TEXT NOT NULL, invite_id TEXT NOT NULL, type TEXT NOT NULL, value TEXT, entered_by TEXT);
-- outreach types: screened | barrier (Pulse PU3: time cost language fear noappt notserious) | sms_sent | call_listed | called
CREATE TABLE IF NOT EXISTS board_decisions (id BIGINT PRIMARY KEY, ts TEXT NOT NULL, county TEXT NOT NULL, key TEXT NOT NULL, title TEXT, decision TEXT NOT NULL, decided_by TEXT, note TEXT);

-- ---------------------------------------------------------------------------------------------------------------------------
-- KPI views (Postgres syntax; for SQLite replace julianday differences). Intervals are computed, never typed (process playbook A2).
CREATE OR REPLACE VIEW pathway_clock AS
SELECT p.id AS pathway_id, p.county, p.cancer, p.language,
       min(e.ts) FILTER (WHERE e.type = 'T0') AS t0,  min(e.ts) FILTER (WHERE e.type = 'T1') AS t1,
       min(e.ts) FILTER (WHERE e.type = 'T2') AS t2,  min(e.ts) FILTER (WHERE e.type = 'T3') AS t3,
       min(e.ts) FILTER (WHERE e.type = 'T4') AS t4,  min(e.ts) FILTER (WHERE e.type = 'T5') AS t5,
       min(e.ts) FILTER (WHERE e.type = 'T6') AS t6
FROM pathways p JOIN events e ON e.pathway_id = p.id GROUP BY p.id, p.county, p.cancer, p.language;

-- Headline: days from first contact to diagnosis (here T0 -> T4; C1 is the earliest 'contact' event when one exists)
CREATE OR REPLACE VIEW kpi_diagnostic_interval AS
SELECT county, cancer, count(*) AS n,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY (t4::timestamptz - t0::timestamptz)) AS median_interval
FROM pathway_clock WHERE t4 IS NOT NULL AND t0 IS NOT NULL GROUP BY county, cancer HAVING count(*) >= 5;   -- n < 5 suppressed

-- Goal 3 (THL 21/2016): share treated within 42 days of referral arrival (T2 -> T6)
CREATE OR REPLACE VIEW kpi_goal3_within_6wk AS
SELECT county, count(*) AS n,
       round(100.0 * count(*) FILTER (WHERE (t6::timestamptz - t2::timestamptz) <= interval '42 days') / count(*), 1) AS pct_within_6wk
FROM pathway_clock WHERE t2 IS NOT NULL AND t6 IS NOT NULL GROUP BY county HAVING count(*) >= 5;

-- Open loops: the latest open_loop event per pathway is 'open'
CREATE OR REPLACE VIEW open_loops AS
SELECT DISTINCT ON (pathway_id) pathway_id, ts, value FROM events WHERE type = 'open_loop' ORDER BY pathway_id, id DESC;

-- ---------------------------------------------------------------------------------------------------------------------------
-- FHIR / OMOP mapping (see also store/schema.py and ingest/fhir.py)
--   pathways      -> Patient (pseudonymous id) + EpisodeOfCare      | OMOP person + observation_period
--   T0 / T1       -> ServiceRequest (category suspicion / referral)  | OMOP observation
--   T2            -> Task (accepted)                                  | OMOP observation
--   T3 / T6       -> Procedure (diagnostic / treatment)               | OMOP procedure_occurrence
--   T4 + stage    -> Condition.recordedDate + Condition.stage         | OMOP condition_occurrence + measurement
--   T5            -> Encounter (type MDT)                             | OMOP visit_occurrence
--   g8            -> Observation (G8 score)                           | OMOP measurement
--   message       -> Communication ; booking -> Appointment ; handover -> Provenance ; coordinator -> CareTeam
--   pulse:PUn     -> QuestionnaireResponse.item (linkId = PUn)        | OMOP observation
