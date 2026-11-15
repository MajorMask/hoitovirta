"""Hoitovirta API + web (one deployable ASGI app). Run: uvicorn api.main:app --port 8000
All data is SYNTHETIC. The simulator advances pathways in real time; every UI polls these endpoints."""
import json
import os
import pathlib
import re
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from act import companion as companion_act, fasttrack, messages, mypath, outreach as outreach_act, pulse_voice, reports as reports_act, slots as slots_act, worklist
from aggregate import board as board_rules, forecast as fc, kpis as agg, role_metrics as rm
from app import ev, i18n, voice
from app.i18n_staff import LANG, loc, loc_deep
from engine import pulse as pulse_engine, scopes as persona_scopes
from engine.domain import (CANCER_LABEL, COORDINATORS, COUNTIES, FLAG_CANCER, FULLNAME, LANGUAGES, RED_FLAGS, STEPS, UTC, fmt_ts, parse_ts)
from sim import cohort, screening as screening_sim
from sim.live import Simulator
from store.board import Board
from store.events import EventStore
from store.screening import Screening
from structure import report
from voice import service as voice_service
from voice import journey_guide
from voice.service import app as voice_app
from ingest import ehr_csv, events as ingest_events, fhir as ingest_fhir

EVENT_TYPES = set(STEPS) | {"stage", "g8", "coordinator", "contact", "booking", "open_loop", "message", "reply", "handover", "slip", "report"}
PULSE_ITEMS = set(pulse_engine.CODEBOOK)
S = {}  # store, sim


TABLES = ["events", "pathways", "outreach_events", "screening_invites", "board_decisions", "task", "voice_call"]   # everything the demo writes (synthetic)


def boot(reset=False):
    """Build (or rebuild) the event store, screening list, board and simulator. reset=True wipes the demo tables first."""
    old = S.get("sim")
    if old:
        old.stop()
    prev = S.get("store")
    db = prev.db if prev else None
    if reset and prev:
        for _ in range(40):   # let write-behind queues drain so nothing is written after the wipe
            if prev.pending_writes() == 0 and S["screening"]._q.qsize() == 0:
                break
            time.sleep(0.5)
        time.sleep(1.5)
        for t in TABLES:
            db.execute(f"delete from {t}")
    store = EventStore(db)
    voice_service.configure_store(store)
    if not store.meta:
        cohort.generate(store, datetime.now(UTC))
    scr = Screening(store.db)
    if not scr.invites:
        screening_sim.generate(scr, store.vnow or datetime.now(UTC))
    sim = Simulator(store)
    sim.screening = scr
    if reset:
        sim.set_clock("paused")
    S.update(store=store, sim=sim, board=Board(store.db), screening=scr)
    if os.getenv("HV_SIM", "1") != "0":
        sim.start()


@asynccontextmanager
async def lifespan(app):
    boot()
    yield
    S["sim"].stop()


app = FastAPI(title="Hoitovirta", lifespan=lifespan)
app.mount("/voice", voice_app, name="voice")


@app.middleware("http")
async def persona_scope(request: Request, call_next):
    """Enforce signed demo-persona scopes before routing and trim JSON fields on the server."""
    path = request.url.path
    if not path.startswith("/api"):
        return await call_next(request)
    scope = persona_scopes.category(path, request.method)
    if path == "/api/kpis" and request.query_params.get("scope") == "national":
        scope = "national_aggregate"
    public = scope == "public"
    token = request.headers.get("x-persona-token")
    payload = persona_scopes.verify_token(token) if token else None
    demo_open = os.getenv("HV_DEMO_OPEN", "0") == "1"
    role = payload.get("role") if payload else ("all" if demo_open and not token else None)
    denied = None
    if not public:
        if not role:
            denied = (401, "persona token required")
        elif not persona_scopes.allowed(role, scope):
            denied = (403, "route not available for this persona")
        elif role in ("patient", "family") and not persona_scopes.pathway_matches(payload, path):
            denied = (403, "pathway outside persona scope")
        elif scope == "unknown":
            denied = (403, "route not scoped")
    if denied:
        _log_scope_refusal(role or "unknown", path)
        return JSONResponse(status_code=denied[0], content={"detail": denied[1]})
    request.state.persona_role = role or "public"
    request.state.persona_token = payload
    response = await call_next(request)
    if role and response.status_code < 400 and response.headers.get("content-type", "").startswith("application/json") and path.startswith(("/api/kpis", "/api/controltower", "/api/national", "/api/worklist", "/api/pathways", "/api/mypath/", "/api/patients")):
        try:
            raw = b"".join([chunk async for chunk in response.body_iterator])
            data = json.loads(raw.decode("utf-8"))
            trimmed = persona_scopes.trim_response(data, role, path, (payload or {}).get("pathway_id"))
            headers = {k: v for k, v in response.headers.items() if k.lower() not in {"content-length", "content-type"}}
            return JSONResponse(trimmed, status_code=response.status_code, headers=headers)
        except (ValueError, TypeError, UnicodeDecodeError):
            pass
    return response


def _log_scope_refusal(role, path):
    st = S.get("store")
    if not st:
        return
    match = re.match(r"/api/(?:mypath|pathways)/([^/]+)", path)
    try:
        st.log_access("persona", role, path, False, match.group(1) if match else "")
    except Exception:
        pass


def _require_persona_path(request: Request, pid: str):
    role = getattr(request.state, "persona_role", "all")
    payload = getattr(request.state, "persona_token", None) or {}
    if role in ("patient", "family") and payload.get("pathway_id") != pid:
        _log_scope_refusal(role, "/api/mypath/" + pid)
        raise HTTPException(403, "pathway outside persona scope")
    if role == "family":
        _log_scope_refusal(role, "/api/mypath/" + pid)
        raise HTTPException(403, "family view is read-only")


@app.middleware("http")
async def staff_language(request, call_next):
    """Staff screens send X-Lang: fi | sv | en. Patient endpoints use their own language handling."""
    lang = request.headers.get("x-lang") or request.query_params.get("lang") or "en"
    tok = LANG.set(lang if lang in ("fi", "sv", "en") else "en")
    try:
        resp = await call_next(request)
    finally:
        LANG.reset(tok)
    # The static files carry Last-Modified 1970 and no Cache-Control, so browsers keep old pages and scripts for years (stale or mixed UI).
    # "no-cache" = always revalidate with the ETag: a cheap 304 when unchanged, the new file as soon as it is deployed.
    if not request.url.path.startswith(("/api", "/voice")):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


ROW_KEYS = {"language_name", "cancer_label", "step_label", "next_label", "loop_reason", "reason", "reasons", "alerts", "flag_label", "label"}
store = lambda: S["store"]  # noqa: E731
sim = lambda: S["sim"]      # noqa: E731


def _need(pid):
    if pid not in store().meta:
        raise HTTPException(404, "unknown pathway")


# ---- meta / health ------------------------------------------------------------------------------
@app.get("/api/health")
def health():
    st, sm = store(), sim()
    return dict(ok=True, synthetic=True, backend=st.db.label, db_error=st.db.error, pending_writes=st.pending_writes(),
                write_errors=st.write_errors, vnow=fmt_ts(st.vnow), pathways=len(st.meta), events=len(st.log),
                sim=dict(running=sm.running, clock=sm.clock_mode, ticks=sm.ticks))


@app.get("/api/meta")
def meta():
    return dict(counties=COUNTIES, coordinators=COORDINATORS, fullnames=FULLNAME,
                red_flags={c: [dict(key=f, label=loc(f)) for f in fl] for c, fl in RED_FLAGS.items()}, flag_cancer=FLAG_CANCER,
                languages={k: loc(v) for k, v in LANGUAGES.items()}, cancers={k: loc(v) for k, v in CANCER_LABEL.items()},
                steps=STEPS, voice=voice.available(), native=i18n.NATIVE, companion=True, synthetic=True)


class PersonaTokenIn(BaseModel):
    role: str
    pathway_id: str | None = None


@app.post("/api/persona-token")
def persona_token(b: PersonaTokenIn):
    if os.getenv("HV_DEMO_OPEN", "0") != "1":
        raise HTTPException(401, "demo persona tokens are disabled; use the configured identity provider")
    try:
        token = persona_scopes.issue_token(b.role, b.pathway_id)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except RuntimeError:
        raise HTTPException(503, "persona signing secret is not configured")
    return {"token": token, "role": b.role, "expires_in": persona_scopes.TOKEN_TTL_SECONDS}


class SimIn(BaseModel):
    clock: str | None = Field(None, pattern="^(paused|normal|fast)$")   # time: frozen, 1 day per 6 h, 1 day per minute
    running: bool | None = None


@app.post("/api/sim")
def sim_control(b: SimIn):
    sm = sim()
    if b.clock:
        sm.set_clock(b.clock)
    if b.running is True:
        sm.start()
    if b.running is False:
        sm.stop()
    return dict(running=sm.running, clock=sm.clock_mode)


class ResetIn(BaseModel):
    confirm: str


@app.post("/api/demo/reset")
def demo_reset(b: ResetIn):
    """Wipe the SYNTHETIC demo data and rebuild a fresh cohort at 'now' (the named demo patients are back at day 12)."""
    if b.confirm != "reset":
        raise HTTPException(422, "send {\"confirm\": \"reset\"}")
    boot(reset=True)
    st = store()
    return dict(ok=True, pathways=len(st.meta), events=len(st.log))


# ---- pathways / worklist ------------------------------------------------------------------------
@app.get("/api/pathways")
def pathways(county: str | None = None, cancer: str | None = None, coordinator: str | None = None, open_loop: bool | None = None,
             done: bool | None = None, limit: int = Query(50, le=500)):
    st = store()
    with st.lock:
        rows = []
        for pid in st.ids():
            f = st.facts(pid)
            if county and f["county"] != county or cancer and f["cancer"] != cancer or coordinator and f["coordinator"] != coordinator:
                continue
            if open_loop is not None and bool(f["open_loop"]) != open_loop or done is not None and f["done"] != done:
                continue
            rows.append(worklist.row(st, pid))
    rows.sort(key=lambda r: -r["priority"])
    return dict(total=len(rows), rows=rows[:limit])


@app.get("/api/pathways/search")
def pathways_search(q: str = "", county: str | None = None, limit: int = Query(12, le=50)):
    """Cheap lookup for pickers: id, name, cancer, where they are now."""
    st = store()
    ql = q.strip().lower()
    out = []
    with st.lock:
        for pid in st.ids():
            f = st.facts(pid)
            if f["done"] or (county and f["county"] != county):
                continue
            if ql and ql not in pid.lower() and ql not in f["name"].lower():
                continue
            out.append(dict(id=pid, name=f["name"], cancer=f["cancer"], county=f["county"], step=f["last_step"], coordinator=f["coordinator"], age=f["age"]))
            if len(out) >= limit:
                break
    return dict(rows=out)


@app.get("/api/pathways/{pid}")
def pathway(pid: str):
    _need(pid)
    return loc_deep(worklist.detail(store(), pid), ROW_KEYS)


@app.get("/api/worklist")
def get_worklist(coordinator: str, limit: int = Query(8, le=50)):
    if not any(coordinator in v for v in COORDINATORS.values()):
        raise HTTPException(404, "unknown coordinator")
    out = loc_deep(worklist.worklist(store(), coordinator, limit), ROW_KEYS)
    out["version"] = store().version
    out["vnow"] = fmt_ts(store().vnow)
    return out


# ---- events ----------------------------------------------------------------------------------------
class EventIn(BaseModel):
    pathway_id: str
    type: str
    value: str | dict | list | None = None
    unit: str | None = None
    source: str | None = "api"
    confidence: float | None = Field(None, ge=0, le=1)
    entered_by: str | None = "api"
    ts: str | None = None


@app.get("/api/events")
def events(since_id: int = 0, pathway_id: str | None = None, limit: int = Query(100, le=1000)):
    st = store()
    with st.lock:
        src = st.events.get(pathway_id, []) if pathway_id else st.log
        src = [e for e in src if e["type"] != "patient_note"]
        rows = [e for e in src if e["id"] > since_id][:limit] if since_id or pathway_id is None else src[-limit:]
        return dict(events=rows, last_id=st.next_id - 1)


@app.post("/api/events")
def post_event(b: EventIn, request: Request):
    _need(b.pathway_id)
    if getattr(request.state, "persona_role", "all") == "patient":
        token = getattr(request.state, "persona_token", None) or {}
        if token.get("pathway_id") != b.pathway_id or b.type != "contact" or b.unit != "reminder" or b.source != "patient-app" or b.entered_by != "patient":
            _log_scope_refusal("patient", "/api/events/" + b.pathway_id)
            raise HTTPException(403, "patient event outside permitted reminder scope")
    if not (b.type in EVENT_TYPES or (b.type.startswith("pulse:") and b.type[6:] in PULSE_ITEMS)):
        raise HTTPException(422, f"unknown event type {b.type}")
    st = store()
    try:
        ts = fmt_ts(parse_ts(b.ts)) if b.ts else fmt_ts(st.vnow)
    except Exception:
        raise HTTPException(422, "bad ts")
    with st.lock:
        e = st.append(b.pathway_id, b.type, ts, b.value, b.unit, b.source, b.confidence, b.entered_by)
        from sim import apply as ap
        ap.scan(st, b.pathway_id, st.vnow)
        sim().schedule(b.pathway_id)
    return e


# ---- fast-track -----------------------------------------------------------------------------------------
@app.get("/api/calls")
def calls(county: str):
    if county not in COUNTIES:
        raise HTTPException(404, "unknown county")
    st = store()
    suggestions = []
    with st.lock:
        for pid, meta in st.meta.items():
            if meta["county"] != county or st.facts(pid)["ts"].get("T0"):
                continue
            sus = [e for e in st.events_for(pid) if e["type"] == "suspicion_suggested"]
            if not sus:
                continue
            suggestions.append(dict(id=pid, pathway_id=pid, name=meta["name"], age=meta["age"], cancer=meta["cancer"],
                                    language=meta["language"], interpreter=meta["interpreter"], says=str(sus[-1]["value"] or ""),
                                    prior=[], suspicion=True))
    return loc_deep(dict(county=county, calls=sim().calls[county], suggestions=suggestions), {"says", "symptom"})


class FastTrackIn(BaseModel):
    call_id: str
    flag: str
    extra_flags: list[str] = []      # more red flags ticked in the same call; the first (flag) sets the pathway
    nurse: str = "Petra"


@app.post("/api/fasttrack")
def post_fasttrack(b: FastTrackIn):
    if b.flag not in FLAG_CANCER or any(f not in FLAG_CANCER for f in b.extra_flags):
        raise HTTPException(422, "unknown red flag")
    call = sim().take_call(b.call_id)
    if not call:
        raise HTTPException(409, "That call was already taken")
    return fasttrack.start(store(), sim(), call, b.flag, b.nurse, extra=b.extra_flags)


class SuggestedFastTrackIn(BaseModel):
    pathway_id: str
    flag: str
    extra_flags: list[str] = []
    nurse: str = "Petra"


@app.post("/api/fasttrack/suggested")
def post_suggested_fasttrack(b: SuggestedFastTrackIn):
    try:
        return fasttrack.start_suggested(store(), sim(), b.pathway_id, b.flag, b.nurse, extra=b.extra_flags)
    except KeyError:
        raise HTTPException(404, "unknown pathway")
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/tasks/{task_id}/done")
def complete_coordinator_task(task_id: str):
    if not store().complete_task(task_id):
        raise HTTPException(404, "unknown task")
    return {"ok": True, "done": True}


# ---- messages / handover -------------------------------------------------------------------------------------
class DraftIn(BaseModel):
    pathway_id: str
    slot: str | None = None


@app.post("/api/messages/draft")
def messages_draft(b: DraftIn):
    _need(b.pathway_id)
    return messages.draft(store(), b.pathway_id, LANG.get(), b.slot)


@app.get("/api/pathways/{pid}/summary")
def pathway_summary(pid: str):
    _need(pid)
    return messages.summary(store(), pid, LANG.get())


class ApproveIn(BaseModel):
    pathway_id: str
    text: str
    text_en: str
    language: str
    engine: str = "Template"
    edited: bool = False
    coordinator: str
    booking: dict


@app.post("/api/messages/approve")
def messages_approve(b: ApproveIn):
    _need(b.pathway_id)
    if b.booking.get("step") not in STEPS or "due" not in b.booking:
        raise HTTPException(422, "bad booking")
    try:
        return messages.approve(store(), sim(), b.pathway_id, b.text, b.text_en, b.language, b.engine, b.edited, b.coordinator, b.booking)
    except ValueError as e:
        raise HTTPException(409, str(e))


class AudioIn(BaseModel):
    pathway_id: str
    text: str = Field(min_length=1, max_length=700)


@app.post("/api/messages/audio")
def messages_audio(b: AudioIn):
    """The coordinator hears the message as the patient will hear it. Limited to short texts on a known pathway."""
    _need(b.pathway_id)
    if not voice.available():
        raise HTTPException(503, "voice is not configured")
    mp3 = voice.speak(b.text)
    if not mp3:
        raise HTTPException(503, "voice is not available right now")
    return Response(mp3, media_type="audio/mpeg")


@app.get("/api/slots")
def get_slots(county: str, kind: str, limit: int = Query(10, le=30)):
    _check(county, None)
    if kind not in ("ct", "imaging", "colonoscopy", "mri", "lab"):
        raise HTTPException(404, "unknown test kind")
    return dict(slots=slots_act.slots(store(), county, kind, store().vnow, limit=limit), free=slots_act.free_counts(store(), county, store().vnow))


@app.get("/api/slots/summary")
def slots_summary(county: str):
    _check(county, None)
    return dict(free=slots_act.free_counts(store(), county, store().vnow), per_day=slots_act.PER_DAY)


class HandoverIn(BaseModel):
    pathway_id: str
    to: str
    by: str
    note: str = ""


@app.post("/api/handover")
def post_handover(b: HandoverIn):
    _need(b.pathway_id)
    if not any(b.to in v for v in COORDINATORS.values()):
        raise HTTPException(422, "unknown coordinator")
    return messages.handover(store(), sim(), b.pathway_id, b.to, b.note, b.by)


# ---- KPIs / pulse / reports --------------------------------------------------------------------------------------
@app.get("/api/kpis")
def get_kpis(scope: str = "county", county: str = "Länsi-Uusimaa", cancer: str | None = None):
    if cancer and cancer not in CANCER_LABEL:
        raise HTTPException(404, "unknown cancer")
    if scope == "national":
        return agg.national(store(), cancer)
    if county not in COUNTIES:
        raise HTTPException(404, "unknown county")
    return agg.kpis(store(), county, cancer)


class PulseIn(BaseModel):
    pathway_id: str
    item: str
    value: str = Field(max_length=500)
    language: str | None = None
    channel: str = "app"
    moment: str | None = None
    confidence: float | None = None


@app.post("/api/pulse")
def post_pulse(b: PulseIn, request: Request):
    _need(b.pathway_id)
    _require_persona_path(request, b.pathway_id)
    if b.item not in PULSE_ITEMS:
        raise HTTPException(422, "item must be PU1..PU10")
    if not pulse_engine.valid(b.item, b.value):
        raise HTTPException(422, f"{b.value!r} is not a valid answer to {b.item}")
    st = store()
    with st.lock:
        e = st.append(b.pathway_id, f"pulse:{b.item}", st.vnow, b.value, unit=b.moment, source=f"pulse:{b.channel}",
                      confidence=b.confidence, entered_by="patient")
    return e


class IngestIn(BaseModel):
    pathway_id: str
    text: str = Field(min_length=3, max_length=8000)
    by: str = "Diagnostics"


class ConfirmIn(BaseModel):
    fields: dict = {}
    include: list[str] = []
    by: str = "Diagnostics"


@app.get("/api/reports/examples")
def report_examples():
    return dict(examples=reports_act.SAMPLES, synthetic=True)


@app.get("/api/reports")
def report_list(county: str | None = None):
    return reports_act.listing(store(), county)


@app.post("/api/reports/ingest")
def report_ingest(b: IngestIn):
    _need(b.pathway_id)
    return loc_deep(reports_act.ingest(store(), sim(), b.pathway_id, b.text, f"diagnostics:{b.by}"), {"saved"})


@app.post("/api/reports/{rid}/confirm")
def report_confirm(rid: str, b: ConfirmIn):
    if any(i not in ("stage", "T4") for i in b.include):
        raise HTTPException(422, "include can only contain stage or T4")
    try:
        return loc_deep(reports_act.confirm(store(), sim(), rid, b.fields, b.include, f"diagnostics:{b.by}"), {"saved"})
    except KeyError:
        raise HTTPException(404, "unknown report")


class ReportIn(BaseModel):
    text: str = Field(min_length=3, max_length=8000)


@app.post("/api/reports/structure")
def reports_structure(b: ReportIn):
    return report.structure(b.text)


@app.get("/api/evidence/{eid}")
def evidence(eid: str):
    if eid not in ev.EV:
        raise HTTPException(404, "unknown evidence id")
    e = ev.get(eid)
    return {k: e.get(k) for k in ("id", "claim", "status", "source", "url", "value", "unit", "short")}


# ---- county Control Tower, National, board -----------------------------------------------------------------
BENCH_IDS = ["lung_seg_patient", "lung_seg_primary", "lung_seg_specialist", "lung_path_fi", "lung_path_dk", "thl_6wk", "no_target_70",
             "se_target_80", "stage_target", "screen_target", "nps_target", "distress_cutoff", "dk_cpp", "equity_flag", "no_delay_data",
             "forecast_loop_days", "step_limits", "rm_252", "rm_123", "rm_312", "screen_breast", "screen_crc", "eq_lang_dom", "eq_lang_oth"]


@app.get("/api/benchmarks")
def benchmarks():
    out = {}
    for i in BENCH_IDS:
        e = ev.get(i)
        out[i] = {k: e.get(k) for k in ("id", "claim", "status", "source", "url", "value", "unit", "short")}
    return out


def _check(county, cancer):
    if county not in COUNTIES:
        raise HTTPException(404, "unknown county")
    if cancer and cancer not in CANCER_LABEL:
        raise HTTPException(404, "unknown cancer")


@app.get("/api/controltower")
def controltower(county: str = "Länsi-Uusimaa", cancer: str | None = None):
    _check(county, cancer)
    st = store()
    k = agg.kpis(st, county, cancer)
    decisions = board_rules.suggest(st, county, cancer)
    state = S["board"].latest(county)
    for d in decisions:
        d["state"] = state.get(d["key"])
    voice_metrics = _voice_metrics(st, county)
    pulse_equity = _pulse_equity(st, county)
    return loc_deep(dict(county=county, cancer=cancer, vnow=fmt_ts(st.vnow), kpis=k,
                         voice_metrics=voice_metrics,
                         segments=dict(patient=k["seg_patient"], primary=k["seg_primary"], specialist=k["seg_specialist"]),
                         equity=agg.equity_by_language(st, county, cancer), pulse_equity=pulse_equity, forecast=fc.forecast(st, county, cancer),
                         decisions=decisions, last_event_id=st.next_id - 1, synthetic=True), {"title", "why", "method", "name"})


def _voice_metrics(st, county):
    now = datetime.now(UTC)
    cutoff = now.timestamp() - 7 * 86400
    calls = 0
    for ts, raw in st.db.query("select ts, raw from voice_call"):
        try:
            fields = json.loads(raw or "{}")
            pathway = fields.get("pathway_id") or fields.get("pathway_code")
            if isinstance(pathway, dict):
                pathway = pathway.get("value")
            calls += bool(pathway in st.meta and st.meta[pathway]["county"] == county
                          and parse_ts(ts).timestamp() >= cutoff)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    no_next = set()
    with st.lock:
        for e in st.log:
            if e["type"] != "pulse:PU4" or e["value"] != "no" or e["pathway_id"] not in st.meta:
                continue
            if st.meta[e["pathway_id"]]["county"] != county:
                continue
            try:
                if parse_ts(e["ts"]).timestamp() >= cutoff:
                    no_next.add(e["pathway_id"])
            except (TypeError, ValueError):
                pass
    return dict(calls_week=calls, pu4_no=len(no_next), synthetic=True)


def _pulse_equity(st, county):
    """Aggregate recent unique Pulse respondents by source channel and pathway language; suppress cells under five."""
    channels = ("app", "phone", "kiosk", "sms")
    eligible = {}
    respondents = {(c, lang): set() for c in channels for lang in LANGUAGES}
    all_respondents, phone_respondents = set(), set()
    with st.lock:
        for pid, meta in st.meta.items():
            if meta["county"] == county:
                eligible[meta["language"]] = eligible.get(meta["language"], 0) + 1
        cutoff = st.vnow.timestamp() - 180 * 86400 if st.vnow else 0
        for e in st.log:
            if not e["type"].startswith("pulse:") or e["pathway_id"] not in st.meta:
                continue
            if st.meta[e["pathway_id"]]["county"] != county:
                continue
            try:
                if parse_ts(e["ts"]).timestamp() < cutoff:
                    continue
            except (TypeError, ValueError):
                continue
            source = (e.get("source") or "pulse:app")
            channel = source.split(":", 1)[1] if source.startswith("pulse:") else "app"
            if channel not in channels:
                channel = "app"
            lang = st.meta[e["pathway_id"]]["language"]
            respondents[(channel, lang)].add(e["pathway_id"])
            all_respondents.add(e["pathway_id"])
            if channel == "phone":
                phone_respondents.add(e["pathway_id"])
    rows = []
    for lang in LANGUAGES:
        den = eligible.get(lang, 0)
        for channel in channels:
            n = len(respondents[(channel, lang)])
            suppressed_cell = n < 5 or den < 5
            rows.append(dict(language=lang, channel=channel, responses=None if suppressed_cell else n,
                             eligible=None if den < 5 else den,
                             rate_pct=round(100 * n / den, 1) if not suppressed_cell and den else None,
                             suppressed=suppressed_cell))
    total = len(all_respondents)
    phone = len(phone_respondents)
    phone_share = round(100 * phone / total, 1) if total >= 5 and phone >= 5 else None
    return dict(rows=rows, phone_share_pct=phone_share,
                phone_share_suppressed=phone_share is None, synthetic=True, window_days=180)


@app.get("/api/rolemetrics")
def role_metrics(role: str, county: str = "Länsi-Uusimaa", coordinator: str = "Laura", programme: str = "breast"):
    """The metric strip for a role (process playbook section B): value, target, and whether the target is met."""
    st = store()
    if role == "national":
        return dict(role=role, metrics=rm.national(st), synthetic=True)
    _check(county, None)
    fn = {"triage": lambda: rm.triage(st, sim(), county), "coordinator": lambda: rm.coordinator(st, county, coordinator),
          "diagnostics": lambda: rm.diagnostics(st, county), "screening": lambda: rm.screening(st, S["screening"], county, programme),
          "county": lambda: rm.county(st, S["board"], county)}.get(role)
    if not fn:
        raise HTTPException(404, "unknown role")
    return dict(role=role, county=county, metrics=fn(), synthetic=True)


@app.get("/api/national")
def get_national(cancer: str | None = None):
    if cancer and cancer not in CANCER_LABEL:
        raise HTTPException(404, "unknown cancer")
    out = agg.national(store(), cancer)
    out["last_event_id"] = store().next_id - 1
    return out


@app.get("/api/activity")
def activity(since_id: int = 0, county: str | None = None):
    """Aggregate counts of what happened since an event id. No pathway ids: safe for county and national views."""
    st = store()
    with st.lock:
        last = st.next_id - 1
        counts = {"events": 0, "pulse": 0, "new_fasttracks": 0, "messages": 0, "open_loops": 0}
        if since_id:
            for e in reversed(st.log):
                if e["id"] <= since_id:
                    break
                if county and st.meta[e["pathway_id"]]["county"] != county:
                    continue
                counts["events"] += 1
                t = e["type"]
                counts["pulse"] += t.startswith("pulse:")
                counts["new_fasttracks"] += (t == "T0")
                counts["messages"] += (t == "message")
                counts["open_loops"] += (t == "open_loop" and '"open"' in (e["value"] or ""))
    return dict(last_id=last, counts=counts)


class BoardIn(BaseModel):
    county: str
    key: str
    title: str
    decision: str = Field(pattern="^(accepted|deferred)$")
    by: str = "County board"
    note: str = ""


@app.post("/api/board")
def post_board(b: BoardIn):
    if b.county not in COUNTIES:
        raise HTTPException(404, "unknown county")
    canon = next((d["title"] for d in board_rules.suggest(store(), b.county) if d["key"] == b.key), b.title)   # always log the canonical English title
    return S["board"].decide(b.county, b.key, canon, b.decision, b.by, b.note)


@app.get("/api/board")
def get_board(county: str):
    if county not in COUNTIES:
        raise HTTPException(404, "unknown county")
    return dict(decisions=[r for r in S["board"].rows if r["county"] == county][-20:])


# ---- Outreach (screening unit) ------------------------------------------------------------------------------------
def _prog(programme):
    if programme not in screening_sim.PROGRAMMES:
        raise HTTPException(404, "unknown programme")


class SmsIn(BaseModel):
    invite_ids: list[str] = Field(max_length=200)
    messages: dict[str, str]
    by: str = "Screening unit"


class IdsIn(BaseModel):
    invite_ids: list[str] = Field(max_length=200)
    by: str = "Screening unit"


class CalledIn2(BaseModel):
    invite_id: str
    by: str = "Screening unit"


class DraftSmsIn(BaseModel):
    programme: str
    language: str


@app.get("/api/outreach/summary")
def outreach_summary(county: str, programme: str = "breast", language: str | None = None):
    _check(county, None)
    _prog(programme)
    return outreach_act.summary(S["screening"], store().vnow, county, programme, language)


@app.get("/api/outreach/list")
def outreach_list(county: str, programme: str = "breast", language: str | None = None, limit: int = Query(30, le=200)):
    _check(county, None)
    _prog(programme)
    return outreach_act.listing(S["screening"], store().vnow, county, programme, language, limit)


@app.get("/api/outreach/calls")
def outreach_calls(county: str, programme: str = "breast"):
    _check(county, None)
    _prog(programme)
    return outreach_act.call_list(S["screening"], store().vnow, county, programme)


@app.post("/api/outreach/draft")
def outreach_draft(b: DraftSmsIn):
    _prog(b.programme)
    if b.language not in LANGUAGES:
        raise HTTPException(404, "unknown language")
    return outreach_act.draft_sms(b.programme, b.language)


@app.post("/api/outreach/send")
def outreach_send(b: SmsIn):
    return outreach_act.send(S["screening"], sim(), b.invite_ids, b.messages, b.by)


@app.post("/api/outreach/calllist")
def outreach_calllist(b: IdsIn):
    return outreach_act.add_calls(S["screening"], b.invite_ids, b.by, store().vnow)


@app.post("/api/outreach/called")
def outreach_called(b: CalledIn2):
    try:
        return outreach_act.mark_called(S["screening"], b.invite_id, b.by, store().vnow)
    except KeyError:
        raise HTTPException(404, "unknown invite")


# ---- patient: My path + Pulse ----------------------------------------------------------------------------------
@app.get("/api/patients")
def demo_patients():
    """Demo sign-in list: the named demo pathways and anyone fast-tracked by a human nurse in this demo."""
    st = store()
    with st.lock:
        rows = [dict(id=pid, name=f["name"], language=f["language"], county=f["county"], cancer=f["cancer"])
                for pid in st.ids() for f in [st.facts(pid)] if f["t0_by"] == "nurse:Petra" and not f["done"]]
    return dict(patients=rows[-12:])


@app.get("/api/i18n/{lang}")
def get_i18n(lang: str):
    if lang not in i18n.NATIVE:
        raise HTTPException(404, "unknown language")
    strings, how = i18n.get(lang)
    return dict(lang=lang, how=how, strings=strings, native=i18n.NATIVE)


@app.get("/api/mypath/{pid}")
def get_mypath(pid: str):
    _need(pid)
    return mypath.view(store(), pid)


@app.get("/api/mypath/{pid}/journey-guide")
def patient_journey_guide(pid: str, lang: str | None = None):
    _need(pid)
    return journey_guide.for_pathway(store(), pid, lang)


class QuestionIn(BaseModel):
    text: str = Field(min_length=1, max_length=500)


class CompanionIn(BaseModel):
    text: str | None = Field(None, min_length=1, max_length=500)
    language: str = "en"
    skill: str | None = None
    arg: str | None = Field(None, max_length=500)


class CompanionConfirmIn(BaseModel):
    need: str = Field(min_length=1, max_length=40)


@app.post("/api/mypath/{pid}/companion")
def post_companion(pid: str, b: CompanionIn, request: Request):
    _need(pid)
    if getattr(request.state, "persona_role", "all") not in ("patient", "all"):
        raise HTTPException(403, "companion is available only in the patient's view")
    if not b.text and not b.skill:
        raise HTTPException(422, "text or skill is required")
    try:
        return companion_act.companion_reply(store(), pid, b.text, b.language, skill=b.skill, arg=b.arg)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/mypath/{pid}/companion/confirm")
def confirm_companion_need(pid: str, b: CompanionConfirmIn, request: Request):
    _need(pid)
    if getattr(request.state, "persona_role", "all") not in ("patient", "all"):
        raise HTTPException(403, "only the patient can confirm companion support")
    try:
        return companion_act.confirm_need(store(), pid, b.need)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/api/mypath/{pid}/companion/moments")
def companion_moments(pid: str, language: str = "en"):
    _need(pid)
    ctx = companion_act._context(store(), pid, language)
    d = mypath.view(store(), pid)
    cards = []
    due = (d.get("next") or {}).get("due")
    label = ctx.get("next_step") or "next appointment"
    key = (d.get("next") or {}).get("key")
    local_steps = {
        "test_colorectal": {"fi": "kolonoskopia", "sv": "koloskopi"}, "test_lung": {"fi": "TT-kuvaus", "sv": "datortomografi"},
        "test_breast": {"fi": "rintojen lisäkuvaus", "sv": "kompletterande bröstbilder"}, "test_prostate": {"fi": "magneettikuvaus", "sv": "MR-undersökning"},
        "test_haematological": {"fi": "verikoe", "sv": "blodprov"},
    }
    label = local_steps.get(key, {}).get(language, label)
    actions = {"en": "Prepare", "fi": "Valmistaudu", "sv": "Förbered dig"}
    if due:
        try:
            days = (parse_ts(due) - store().vnow).total_seconds() / 86400
        except (TypeError, ValueError):
            days = None
        if days is not None and 0 <= days <= 7:
            kind = "prep_due" if days <= 1 else "countdown"
            count = max(0, int(days))
            text = (f"Seuraava vaiheesi, {label}, on {count} päivän kuluttua." if language == "fi" else
                    f"Ditt nästa steg, {label}, är om {count} dagar." if language == "sv" else
                    f"Your {label} is in {count} days.")
            cards.append(dict(id=f"{pid}:{kind}", kind=kind, text=text,
                              actions=[dict(label=actions.get(language, "Prepare"), skill="prepare", arg=None)]))
    recent = [e for e in store().events_for(pid) if e["type"] in ("T1", "T2", "T3", "T4", "T5", "T6")]
    if recent and not cards:
        try:
            age_hours = (store().vnow - parse_ts(recent[-1]["ts"])).total_seconds() / 3600
        except (TypeError, ValueError):
            age_hours = 999
        if 0 <= age_hours <= 24:
            step = recent[-1]["type"]
            if step in ("T1", "T2"):
                guide = ctx.get("journey_guide") or {}
                text = guide.get("what_is_happening", "A new step was recorded in your care path.")
                action_label = {"en": "See my next step", "fi": "Katso seuraava vaihe", "sv": "Se nästa steg"}.get(language, "See my next step")
                cards.append(dict(id=f"{pid}:stage_change", kind="stage_change", text=text,
                                  actions=[dict(label=action_label, skill="where_am_i", arg=None)]))
            else:
                text = {"en": "How did the visit go?", "fi": "Miten käynti sujui?", "sv": "Hur gick besöket?"}.get(language, "How did the visit go?")
                action_label = {"en": "Tell us", "fi": "Kerro meille", "sv": "Berätta"}.get(language, "Tell us")
                cards.append(dict(id=f"{pid}:after_visit", kind="after_visit", text=text,
                                  actions=[dict(label=action_label, skill="after_visit", arg=None)]))
    if not cards:
        quiet = {"en": "No new step to act on right now.", "fi": "Uutta hoidettavaa vaihetta ei ole juuri nyt.", "sv": "Det finns inget nytt steg att agera på just nu."}.get(language, "No new step to act on right now.")
        cards = [dict(id=f"{pid}:quiet", kind="quiet", text=quiet, actions=[])]
    language_note = "English fallback" if language == "so" else None
    if language in ("ar", "ru") and cards:
        translation = companion_act._result(cards[0]["text"], "where_am_i", "none", [], [])
        translation["cards"] = [dict(kind="steps", title="", items=[cards[0]["text"]])]
        translation["follow_ups"] = [dict(label=a["label"], skill=a["skill"], arg=a.get("arg")) for a in cards[0]["actions"]]
        translation = companion_act._translate_skill(translation, ctx, language, time.perf_counter())
        if translation.get("language_note") == "Machine translated":
            cards[0]["text"] = translation["cards"][0]["items"][0]
            for action, follow in zip(cards[0]["actions"], translation["follow_ups"]):
                action["label"] = follow["label"]
            language_note = "Machine translated"
        else:
            language_note = "English fallback"
    return dict(cards=cards[:2], language_note=language_note, synthetic=True)


class NoteIn(BaseModel):
    text: str = Field(min_length=1, max_length=1000)
    share: bool = False


@app.get("/api/mypath/{pid}/notes")
def get_companion_notes(pid: str, request: Request):
    _need(pid)
    role = getattr(request.state, "persona_role", "all")
    notes = []
    for event in store().events_for(pid):
        if event["type"] != "patient_note" or not event.get("value"):
            continue
        try:
            note = json.loads(event["value"])
        except (TypeError, ValueError):
            continue
        if role == "family" and not note.get("share"):
            continue
        notes.append(dict(text=note.get("text", ""), ts=event["ts"], share=bool(note.get("share"))))
    return dict(notes=notes[-50:], synthetic=True)


@app.post("/api/mypath/{pid}/notes")
def save_companion_note(pid: str, b: NoteIn, request: Request):
    _need(pid)
    if getattr(request.state, "persona_role", "all") != "patient":
        raise HTTPException(403, "only the patient can save a note")
    store().append(pid, "patient_note", store().vnow, {"text": b.text.strip(), "share": b.share}, source="companion", entered_by="patient")
    return dict(ok=True, shared=b.share)


@app.post("/api/mypath/{pid}/question")
def post_question(pid: str, b: QuestionIn):
    _need(pid)
    try:
        return mypath.question(store(), sim(), pid, b.text)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/api/mypath/{pid}/thread")
def get_thread(pid: str):
    _need(pid)
    return mypath.thread(store(), pid)


class ReplyIn(BaseModel):
    pathway_id: str
    text: str = Field(min_length=1, max_length=700)
    language: str
    coordinator: str


@app.get("/api/messages/reply_draft")
def reply_draft(pathway_id: str):
    _need(pathway_id)
    return messages.reply_draft(store(), pathway_id)


@app.post("/api/messages/reply")
def reply_send(b: ReplyIn):
    _need(b.pathway_id)
    try:
        return messages.reply_send(store(), sim(), b.pathway_id, b.text, b.language, b.coordinator)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/mypath/{pid}/slip")
def post_slip(pid: str):
    _need(pid)
    return mypath.slip(store(), sim(), pid)


@app.get("/api/mypath/{pid}/audio")
def get_audio(pid: str, what: str = "next", lang: str = "en"):
    _need(pid)
    if what not in ("next", "message") or lang not in i18n.NATIVE:
        raise HTTPException(422, "bad request")
    if not voice.available():
        raise HTTPException(503, "voice is not configured")
    text = mypath.audio_text(store(), pid, what, lang)
    if not text:
        raise HTTPException(404, "nothing to read")
    mp3 = voice.speak(text)
    if not mp3:
        raise HTTPException(503, "voice is not available right now")
    return Response(mp3, media_type="audio/mpeg")


@app.post("/api/pulse/voice")
async def pulse_from_voice(request: Request, pathway_id: str, item: str, lang: str = "en"):
    """Raw audio body (webm/mp4/wav). Returns a PROPOSED answer: the patient must confirm it before it is saved."""
    _need(pathway_id)
    _require_persona_path(request, pathway_id)
    if item not in pulse_engine.CODEBOOK:
        raise HTTPException(422, "unknown item")
    if not voice.available():
        raise HTTPException(503, "voice is not configured")
    body = await request.body()
    if not body or len(body) > 8_000_000:
        raise HTTPException(422, "no audio or too large")
    mime = request.headers.get("content-type", "audio/webm").split(";")[0]
    text, _ = voice.transcribe(body, filename="answer." + mime.split("/")[-1], mime=mime)
    if not text:
        return dict(transcript=None, value=None, confidence=0.0)
    if item == "PU9b":
        return dict(transcript=text[:500], value=text[:500], confidence=0.9, engine="transcription")
    out = pulse_voice.map_answer(item, text, lang)
    return dict(transcript=text, **out)


class CalledIn(BaseModel):
    coordinator: str


@app.post("/api/pathways/{pid}/called")
def post_called(pid: str, b: CalledIn):
    _need(pid)
    return messages.called(store(), sim(), pid, b.coordinator)


# ---- ingest adapters (EHR export CSV, FHIR Bundle) ---------------------------------------------------------------
@app.post("/api/ingest/ehr-csv")
async def ingest_csv(request: Request):
    """Body: CSV text (see ingest/ehr_csv.py). Idempotent. SYNTHETIC samples only in this prototype."""
    body = (await request.body()).decode("utf-8", "replace")
    if len(body) > 2_000_000:
        raise HTTPException(413, "file too large")
    try:
        return ingest_events.ingest_events(store(), sim(), ehr_csv.rows_from_csv(body), "ingest:ehr-csv")
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.post("/api/ingest/fhir")
async def ingest_fhir_bundle(bundle: dict):
    try:
        return ingest_events.ingest_events(store(), sim(), ingest_fhir.rows_from_bundle(bundle), "ingest:fhir")
    except ValueError as e:
        raise HTTPException(422, str(e))


# ---- web ------------------------------------------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(ROOT / "web" / "index.html")


# The Pulse check-in survey sidecar (mock, in memory, DEMO ids only) is mounted under its own path: it shares nothing with the event store above.
from pulse_service.main import app as pulse_lab_app
app.mount("/pulse-lab", pulse_lab_app, name="pulse-lab")
app.mount("/", StaticFiles(directory=ROOT / "web"), name="web")
