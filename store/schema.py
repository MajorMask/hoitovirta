"""Event store schema. Append-only: events are never updated or deleted. All data is SYNTHETIC.

event(id, pathway_id, ts, type, value, unit, source, confidence, entered_by)
Types: T0..T6 (pathway timestamps), stage, g8, coordinator, contact, booking, open_loop, message, handover, slip, pulse:PU1..PU10.

FHIR mapping (comment table, for the national repository):
  pathways.id            -> Patient.id (pseudonymous) / EpisodeOfCare.id
  event T0 / T1 / T2     -> ServiceRequest.authoredOn (suspicion) / referral sent / Task (referral received)
  event T3               -> Procedure.performedDateTime (first test)
  event T4               -> Condition.recordedDate (diagnosis) ; stage -> Observation (TNM stage group)
  event T5 / T6          -> Encounter (MDT) / Procedure or MedicationAdministration (first treatment)
  event g8, coordinator  -> Observation (G8 score) / CareTeam.participant
  event message          -> Communication ; booking -> Appointment ; handover -> Provenance
  event pulse:PUn        -> QuestionnaireResponse.item (linkId = PUn)
OMOP: pathways -> person + observation_period; events -> procedure_occurrence / condition_occurrence / observation.
"""
EVENTS_DDL = """create table if not exists events (
  id bigint primary key,
  pathway_id text not null,
  ts text not null,
  type text not null,
  value text,
  unit text,
  source text,
  confidence real,
  entered_by text)"""
EVENTS_IDX = "create index if not exists events_pathway on events (pathway_id)"
PATHWAYS_DDL = """create table if not exists pathways (
  id text primary key,
  name text, age integer, sex text, language text, county text, cancer text,
  onset_days integer, interpreter integer)"""

VOICE_CALL_DDL = """create table if not exists voice_call (
  conversation_id text primary key, ts text not null, caller_type text, language text,
  summary text, review_needed integer not null default 0, raw text)"""
TASK_DDL = """create table if not exists task (
  id text primary key, pathway_id text, ts text not null, kind text not null,
  detail text, done integer not null default 0, assigned_to text)"""
TASK_IDX = "create index if not exists task_assigned on task (assigned_to, done, ts)"
ACCESS_LOG_DDL = """create table if not exists access_log (
  id text primary key, ts text not null, staff_id text, role text, action text,
  ok integer not null, pathway_id text)"""
