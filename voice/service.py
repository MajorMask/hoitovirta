"""Hoitovirta voice line: tool webhooks + post-call receiver.
Mounted at /voice in the main FastAPI app (api.main:app).
ElevenLabs agent calls the /tool/* endpoints during a call and POSTs /post-call after it.
All data here is SYNTHETIC. Real use would need strong staff auth (see the voice service spec)."""
import hashlib, hmac, json, os, re, secrets, time, uuid
import threading
from collections import defaultdict, deque
from datetime import date, datetime, timezone
from pathlib import Path
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from engine.domain import FULLNAME, PLACES, STEPS, step_name
from engine import pulse as pulse_engine
from engine import safety
from app import i18n
from voice import journey_guide
from store.events import EventStore

WEBHOOK_SECRET = os.environ.get("ELEVENLABS_WEBHOOK_SECRET", "")   # from ElevenLabs post-call webhook
TOOL_SECRET = os.environ.get("VOICE_TOOL_SECRET", "")               # sent by the agent as header x-tool-secret
DEMO_OPEN = os.environ.get("HV_DEMO_OPEN") == "1"
RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_BUCKETS = defaultdict(deque)
RATE_LOCK = threading.Lock()
STORE = None
POST_CALL_LOCK = threading.Lock()
POST_CALL_IDS = set()


def configure_store(store):
    """Use the running app's shared event store. Standalone use lazily creates the same store layer."""
    global STORE
    STORE = store


def _store():
    global STORE
    if STORE is None:
        STORE = EventStore()
    return STORE

# ---- synthetic directory (replace with real IAM in production) -------------
_SEED = Path(__file__).resolve().parents[1] / "data" / "seed_voice.json"
with _SEED.open(encoding="utf-8") as _f:
    STAFF = {r["id"]: (r["pin"], r["name"], r["role"]) for r in json.load(_f)["staff"]}
# role -> what the agent may read out. Principle: least information for the job.
SCOPES = {
    "coordinator": {"patient_status", "patient_contact", "sop"},
    "triage_nurse": {"patient_status", "sop"},
    "oncologist": {"patient_status", "sop"},
    "surgeon": {"patient_status", "sop"},
    "admin": {"sop"},
    "county_manager": {"aggregates", "sop"},
}
SESSIONS = {}  # token -> (staff_id, role, expires)
SOPS = {
    "suspicion": "SOP-1 Point of suspicion: the clock (T0) starts when a clinician records suspected cancer or taps a red flag in Fast-track. Owner: triage nurse or GP. Deadline: same day. Next: coordinator is named within 1 working day.",
    "handover": "SOP-2 Coordinator and handover: the current owner keeps responsibility until the next person confirms contact. Name the coordinator to the patient within 1 working day.",
    "result": "SOP-3 Closed loop: every abnormal or suspicious result gets a next step booked within 7 days, or it goes on the coordinator's Today list.",
    "redflag": "SOP-4 Triage red flags: use the red-flag list for the cancer type. Third contact for the same complaint: consider a direct test instead of another visit.",
    "screening": "SOP-5 Screening follow-up: SMS in own language, then a call, then an evening or weekend slot, then a community partner.",
    "language": "SOP-6 Language access: if the interpreter flag is set, book an interpreter by default and send messages in the patient's language, approved by a person.",
}

app = FastAPI(title="Hoitovirta voice line")


@app.middleware("http")
async def limit_voice_requests(request: Request, call_next):
    """Simple per-client rate limit for voice tools and post-call webhook."""
    if request.url.path.startswith("/tool/") or request.url.path in ("/post-call", "/outbound"):
        peer = request.client.host if request.client else "unknown"
        key = (peer, request.url.path)
        now = time.monotonic()
        with RATE_LOCK:
            q = RATE_BUCKETS[key]
            while q and now - q[0] >= RATE_LIMIT_WINDOW_SECONDS:
                q.popleft()
            if len(q) >= RATE_LIMIT_REQUESTS:
                return JSONResponse(status_code=429, content={"detail": "rate limit exceeded"}, headers={"Retry-After": str(RATE_LIMIT_WINDOW_SECONDS)})
            q.append(now)
    return await call_next(request)


# ---- storage -----------------------------------------------------------------
def emit(store, pathway_id, typ, value, unit=None, conf=1.0, by="voice-agent", source="elevenlabs-voice"):
    if pathway_id not in store.meta:
        return None
    return store.append(pathway_id, typ, datetime.now(timezone.utc), str(value), unit=unit,
                        source=source, confidence=conf, entered_by=by)


def log_access(store, staff_id, role, action, ok, pathway_id=""):
    store.log_access(staff_id, role, action, ok, pathway_id)


def _patient_record(store, code):
    if code not in store.meta:
        return None
    meta = store.meta[code]
    facts = store.facts(code)
    view = store.view(code)
    booking = facts["booking"]
    next_step = facts["next_step"]
    if next_step in ("T1", "T2", "T3"):
        next_step = "T3"  # patient-facing next action is the first test, not referral plumbing
    coord = facts["coordinator"]
    return dict(birth_year=datetime.now().year - int(meta["age"]), next=step_name(meta["cancer"], next_step) if next_step else None,
                when=booking.get("due") if booking else None, place=PLACES.get(meta["county"]),
                nurse=FULLNAME.get(coord, coord) if coord else None, language=meta["language"],
                interpreter=bool(meta["interpreter"]), stage_known=facts["stage"] is not None,
                coordinator=coord, cancer=meta["cancer"], view=view)


def _task_owner(store, pathway_id):
    if pathway_id in store.meta:
        owner = store.facts(pathway_id)["coordinator"]
        if owner:
            return owner
    return "Laura"  # synthetic demo fallback for unassigned or unmatched callers


def _check_tool_secret(x_tool_secret):
    if not TOOL_SECRET or not WEBHOOK_SECRET:
        if DEMO_OPEN:
            return
        raise HTTPException(503, "voice line not configured")
    if not hmac.compare_digest(x_tool_secret or "", TOOL_SECRET):
        raise HTTPException(401, "bad tool secret")


def _session(token, need):
    s = SESSIONS.get(token)
    if not s or s[2] < time.time():
        return None, "Session expired. Ask the caller to verify again."
    if need not in SCOPES[s[1]]:
        return None, f"Role {s[1]} is not allowed to hear this."
    return s, None


# ---- tools the agent calls during the call -----------------------------------
@app.post("/tool/verify_staff")
async def verify_staff(req: Request, x_tool_secret: str = Header(None)):
    _check_tool_secret(x_tool_secret)
    b = await req.json()
    sid = re.sub(r"[\s]", "", str(b.get("staff_id", ""))).upper()
    pin = re.sub(r"\D", "", str(b.get("pin", "")))
    st = _store()
    rec = STAFF.get(sid)
    ok = bool(rec) and hmac.compare_digest(rec[0], pin)
    log_access(st, sid, rec[2] if rec else "", "verify", ok)
    if not ok:
        return {"verified": False, "message": "I could not verify that. Please check the ID and code, or call the switchboard."}
    token = secrets.token_urlsafe(12)
    SESSIONS[token] = (sid, rec[2], time.time() + 900)
    return {"verified": True, "name": rec[1], "role": rec[2], "session_token": token,
            "may_hear": sorted(SCOPES[rec[2]]),
            "message": f"Verified: {rec[1]}, {rec[2].replace('_', ' ')}."}


@app.post("/tool/patient_status")
async def patient_status(req: Request, x_tool_secret: str = Header(None)):
    """Staff: needs session + pathway code. Patient: pathway code + birth year (no session)."""
    _check_tool_secret(x_tool_secret)
    b = await req.json()
    code = str(b.get("pathway_code", "")).upper().replace(" ", "")
    st = _store()
    p = _patient_record(st, code)
    if b.get("session_token"):
        s, err = _session(b["session_token"], "patient_status")
        if err:
            log_access(st, "", "", "patient_status", False, code)
            return {"allowed": False, "message": err}
        log_access(st, s[0], s[1], "patient_status", bool(p), code)
        if not p:
            return {"allowed": True, "found": False, "message": "No pathway with that code."}
        out = dict(next_step=p["next"], when=p["when"], place=p["place"], coordinator=p["nurse"],
                   language=p["language"], interpreter=p["interpreter"], stage_known=p["stage_known"])
        return {"allowed": True, "found": True, **out}
    # patient / relative: two-factor in plain words = code + birth year
    ok = bool(p) and str(b.get("birth_year", "")) == str(p["birth_year"])
    log_access(st, "patient", "patient", "patient_status", ok, code)
    if not ok:
        return {"allowed": False, "message": "I could not match that. I can still help in general terms."}
    return {"allowed": True, "found": True, "next_step": p["next"], "when": p["when"], "place": p["place"],
            "coordinator": p["nurse"], "interpreter": p["interpreter"]}


@app.post("/tool/sop_lookup")
async def sop_lookup(req: Request, x_tool_secret: str = Header(None)):
    _check_tool_secret(x_tool_secret)
    b = await req.json()
    token = b.get("session_token")
    session = SESSIONS.get(token) if token else None
    log_access(_store(), session[0] if session else "", session[1] if session else "caller", "sop_lookup", True)
    q = str(b.get("situation", "")).lower()
    keys = [k for k, words in {
        "suspicion": ["suspect", "suspicion", "clock", "t0", "fast"], "handover": ["handover", "coordinator", "owner"],
        "result": ["result", "abnormal", "report", "loop", "finding"], "redflag": ["red flag", "third", "repeat", "symptom"],
        "screening": ["screen", "invite", "fit", "mammo"], "language": ["interpreter", "language", "translate"]}.items()
        if any(w in q for w in words)]
    if not keys:
        return {"found": False, "message": "The SOPs do not cover that. Do not guess. Ask the coordinator or the medical lead."}
    return {"found": True, "sops": [SOPS[k] for k in keys],
            "note": "This is the procedure, not a clinical decision. Treatment and diagnosis choices stay with the clinician and the MDT."}


@app.post("/tool/pulse_questions")
async def pulse_questions(req: Request, x_tool_secret: str = Header(None)):
    """Expose the app's canonical Pulse items/options for a single phone moment."""
    _check_tool_secret(x_tool_secret)
    b = await req.json()
    moment, lang = str(b.get("moment", "")), str(b.get("language", "en"))
    if moment not in pulse_engine.MOMENTS:
        raise HTTPException(422, "unknown Pulse moment")
    T, _ = i18n.get(lang)
    items = []
    for item in pulse_engine.MOMENTS[moment][:2]:
        kind, options = pulse_engine.CODEBOOK[item]
        items.append({"item": item, "question": T.get(f"q_{item}", T.get(f"q_{item}", item)),
                      "kind": kind, "options": [{"key": key, "label": T.get(f"opt_{item}_{key}", key)} for key in options]})
    return {"moment": moment, "items": items, "synthetic": True}


@app.post("/tool/journey_guide")
async def journey_guide_tool(req: Request, x_tool_secret: str = Header(None)):
    """Return the current pathway stage's sourced example text for the agent to read aloud."""
    _check_tool_secret(x_tool_secret)
    b = await req.json()
    pathway_id = str(b.get("pathway_id", ""))
    if pathway_id not in _store().meta:
        raise HTTPException(404, "unknown pathway")
    guide = journey_guide.for_pathway(_store(), pathway_id, str(b.get("language", "en")))
    return {**guide, "spoken_text": journey_guide.spoken_text(guide)}


# ---- post-call: structured data -> pipeline ------------------------------------
def _verify_signature(body: bytes, header: str):
    if not WEBHOOK_SECRET:
        return DEMO_OPEN
    try:
        parts = dict(p.split("=", 1) for p in header.split(","))
        t, v0 = parts["t"], parts["v0"]
    except Exception:
        return False
    if abs(time.time() - int(t)) > 30 * 60:
        return False
    mac = hmac.new(WEBHOOK_SECRET.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, v0)


def _val(d, k):
    v = d.get(k)
    return v.get("value") if isinstance(v, dict) else v


def _onset_pulse_choice(value):
    """Convert a valid ISO onset date to the existing PU1 interval key; unknown dates stay in voice_call.raw."""
    try:
        onset = date.fromisoformat(str(value)[:10])
        days = (datetime.now(timezone.utc).date() - onset).days
    except (TypeError, ValueError):
        return None
    if days < 0:
        return None
    if days <= 7:
        return "week"
    if days <= 28:
        return "w2_4"
    if days <= 90:
        return "m1_3"
    return "m3p"


def _emit_intake_pulse(store, pathway_id, item, value, moment, confidence):
    if pulse_engine.valid(item, str(value)):
        return emit(store, pathway_id, f"pulse:{item}", str(value), moment, confidence,
                    by="voice-agent", source="elevenlabs-voice")
    return None


@app.post("/post-call")
async def post_call(req: Request, elevenlabs_signature: str = Header(None, alias="ElevenLabs-Signature")):
    if (not TOOL_SECRET or not WEBHOOK_SECRET) and not DEMO_OPEN:
        raise HTTPException(503, "voice line not configured")
    raw = await req.body()
    if not _verify_signature(raw, elevenlabs_signature or ""):
        raise HTTPException(401, "bad signature")
    payload = json.loads(raw)
    data = payload.get("data", payload)
    conv = data.get("conversation_id", str(uuid.uuid4()))
    st = _store()
    with POST_CALL_LOCK:
        prior = st.db.query("select review_needed from voice_call where conversation_id=?", (conv,))
        if conv in POST_CALL_IDS or prior:
            stored_review = bool(prior[0][0]) if prior else False
            pid = None
            if prior:
                call = st.db.query("select raw from voice_call where conversation_id=?", (conv,))
                try:
                    raw_result = json.loads(call[0][0] or "{}")
                    pid = raw_result.get("pathway_id") or raw_result.get("pathway_code")
                except (IndexError, TypeError, ValueError):
                    pid = None
            return {"ok": True, "pathway_id": pid, "needs_check": stored_review, "duplicate": True}
        POST_CALL_IDS.add(conv)
    dc = (data.get("analysis") or {}).get("data_collection_results") or data.get("collected") or {}
    g = lambda k: _val(dc, k)
    caller = g("caller_type") or "unknown"
    code = (g("pathway_id") or g("pathway_code") or "").upper().replace(" ", "")
    pid = code if code in st.meta else f"VC-{conv[-8:]}"  # unmatched callers get a provisional id
    conf_missing = [k for k in ("symptom_onset_date", "worry_0_10") if g(k) in (None, "", "unknown")]
    review = int(bool(conf_missing) or g("caller_confirmed_summary") is False)
    if caller in ("patient", "relative"):
        if g("symptom_onset_date"):
            onset_choice = _onset_pulse_choice(g("symptom_onset_date"))
            if onset_choice:
                _emit_intake_pulse(st, pid, "PU1", onset_choice, "first_contact", 0.6 if review else 0.85)
        if g("contacts_so_far") is not None:
            try:
                count = int(g("contacts_so_far"))
                contacts_value = "1" if count <= 1 else "2" if count == 2 else "3p"
                _emit_intake_pulse(st, pid, "PU2", contacts_value, "first_contact", 0.8)
            except (TypeError, ValueError):
                pass
        if g("knows_next_step") is not None:
            value = g("knows_next_step")
            answer = "yes" if value is True else "no" if value is False else str(value).lower()
            _emit_intake_pulse(st, pid, "PU4", answer, "suspicion", 0.9)
        if g("worry_0_10") not in (None, ""):
            _emit_intake_pulse(st, pid, "PU7", g("worry_0_10"), "suspicion", 0.85)
        symptom_text = " ".join(str(g(k) or "") for k in ("symptom_summary", "red_flags_mentioned", "call_summary"))
        urgent_match = safety.is_urgent(symptom_text)
        if g("red_flags_mentioned") or urgent_match:
            reported_phrase = g("red_flags_mentioned") or g("symptom_summary") or "shared emergency phrase matched"
            emit(st, pid, "suspicion_suggested", reported_phrase, None, 0.6)
            summary = g("call_summary") or ""
            detail = (f"URGENT SAFETY: a voice report matched the shared emergency phrase list. Confirm safety guidance and review promptly. {summary} "
                      "A clinician decides whether to start fast-track (T0)." if urgent_match else
                      f"Caller mentioned: {g('red_flags_mentioned')}. {summary} A clinician decides whether to start fast-track (T0).").strip()
            st.add_task(pid, "triage_review", detail, assigned_to=_task_owner(st, pid))
        try:
            worry = float(g("worry_0_10"))
        except (TypeError, ValueError):
            worry = None
        if (worry is not None and worry >= 4) or g("wants_callback"):
            summary = g("call_summary") or ""
            detail = f"Call back within 1 working day. Worry {g('worry_0_10')}/10. {summary}".strip()
            st.add_task(pid, "callback", detail, assigned_to=_task_owner(st, pid))
    # Pulse mode stores confirmed answers with the exact app event names and a phone channel.
    moment = g("moment")
    if caller in ("patient", "relative") and code in st.meta and moment in pulse_engine.MOMENTS:
        for idx, item in enumerate(pulse_engine.MOMENTS[moment][:2], start=1):
            answer = g(f"pulse_answer_{idx}")
            if answer in (None, "") or not pulse_engine.valid(item, str(answer)):
                continue
            emit(st, pid, f"pulse:{item}", str(answer), moment, 0.95, by="patient", source="pulse:phone")
            if item == "PU7" and float(answer) >= pulse_engine.DISTRESS_CUTOFF:
                summary = g("call_summary") or f"Phone Pulse worry {answer}/10."
                st.add_task(pid, "callback", f"Call back within 1 working day. Phone Pulse worry {answer}/10. {summary}".strip(),
                            assigned_to=_task_owner(st, pid))
    st.add_voice_call(conv, datetime.now(timezone.utc).isoformat(), caller, g("language") or "",
                      g("call_summary") or "", review, json.dumps(dc, ensure_ascii=False)[:20000])
    with POST_CALL_LOCK:
        POST_CALL_IDS.discard(conv)
    return {"ok": True, "pathway_id": pid, "needs_check": bool(review)}


@app.post("/outbound")
async def outbound(req: Request, x_tool_secret: str = Header(None)):
    """Dry-run only. Telephony is deliberately not connected in this prototype."""
    _check_tool_secret(x_tool_secret)
    b = await req.json()
    pathway_id = str(b.get("pathway_id", ""))
    moment = str(b.get("moment", ""))
    if pathway_id not in _store().meta or moment not in pulse_engine.MOMENTS:
        raise HTTPException(422, "unknown pathway or Pulse moment")
    return {"ok": True, "dry_run": True, "call_placed": False, "pathway_id": pathway_id, "moment": moment,
            "message": "No outbound call placed. User decision required for telephony provider, number, cost, and consent text."}


@app.get("/health")
def health():
    return {"ok": True}
