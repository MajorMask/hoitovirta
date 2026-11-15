"""Offline integration test: voice records use the shared event store. No ElevenLabs needed."""
import ast, os, sys, json, pathlib, time
from datetime import datetime, timezone
TEST_DB = "/tmp/voice_test.db"
os.environ["HV_FORCE_SQLITE"] = "1"
os.environ["HV_DEMO_OPEN"] = "1"  # Explicitly open local synthetic tests only.
# Keep real local/Modal credentials out of this offline suite. A configured secret
# must not make the synthetic TestClient requests require an unknown header.
os.environ["VOICE_TOOL_SECRET"] = ""
os.environ["ELEVENLABS_WEBHOOK_SECRET"] = ""
if os.path.exists(TEST_DB): os.remove(TEST_DB)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))
from fastapi.testclient import TestClient
from app.store import DB
from store.events import EventStore
import service
from voice import journey_guide
from voice import agent_config
assert "I am an AI assistant" in agent_config.FIRST_MESSAGE
assert "call 112" in agent_config.PROMPT and "never advise on treatment or medicines" in agent_config.PROMPT
assert "never diagnose" in agent_config.PROMPT.lower()
# Static guard: no voice Python call may pass a literal T0 to append/emit.
for source_file in pathlib.Path(ROOT, "voice").rglob("*.py"):
    if source_file.name.startswith("test_"):
        continue
    tree = ast.parse(source_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and getattr(node.func, "attr", "") in ("append", "emit"):
            assert not any(isinstance(arg, ast.Constant) and arg.value == "T0" for arg in node.args), f"voice T0 write in {source_file}"
assert len(journey_guide.GUIDE["stages"]) == 8
for guide_entry in journey_guide.GUIDE["stages"].values():
    assert guide_entry["source_url"].startswith("https://") and guide_entry["review_status"] == "example text, not clinically reviewed"
    for lang_code in ("en", "fi"):
        assert all(k in guide_entry[lang_code] for k in journey_guide.FIELDS)
        assert len(guide_entry[lang_code]["myths"]) == 3

store = EventStore(DB(sqlite_path=TEST_DB))
store.add_pathway(dict(id="PW-D1", name="Amina H.", age=67, sex="f", language="ar", county="Länsi-Uusimaa",
                       cancer="colorectal", onset_days=12, interpreter=True))
store.append("PW-D1", "T0", datetime.now(timezone.utc), "Positive FIT", unit="flag", source="triage", entered_by="nurse")
store.append("PW-D1", "coordinator", datetime.now(timezone.utc), "Laura", source="fast-track", entered_by="nurse")
service.configure_store(store)
c = TestClient(service.app)
assert c.get("/health").json() == {"ok": True}

# staff: wrong pin, then right pin
assert c.post("/tool/verify_staff", json={"staff_id": "L-1042", "pin": "0000"}).json()["verified"] is False
v = c.post("/tool/verify_staff", json={"staff_id": "l 1042".replace(" ", "-"), "pin": "4821"}).json()
assert v["verified"] and v["role"] == "coordinator", v
tok = v["session_token"]
assert tok != "" and service.SESSIONS[tok][0] == "L-1042" and service.SESSIONS[tok][1] == "coordinator"
s = c.post("/tool/patient_status", json={"pathway_code": "pw-d1", "session_token": tok}).json()
assert s["found"] and s["next_step"] == "Colonoscopy" and "coordinator_phone" not in s, s
# admin must NOT hear patient status
a = c.post("/tool/verify_staff", json={"staff_id": "A-5001", "pin": "2678"}).json()
assert a["session_token"] != tok and service.SESSIONS[a["session_token"]][0] == "A-5001"
r = c.post("/tool/patient_status", json={"pathway_code": "PW-D1", "session_token": a["session_token"]}).json()
assert r["allowed"] is False, r
# triage nurse hears status but no phone
t = c.post("/tool/verify_staff", json={"staff_id": "T-2210", "pin": "7305"}).json()
r = c.post("/tool/patient_status", json={"pathway_code": "PW-D1", "session_token": t["session_token"]}).json()
assert r["found"] and "coordinator_phone" not in r, r
# patient: wrong birth year, right birth year
assert c.post("/tool/patient_status", json={"pathway_code": "PW-D1", "birth_year": "1999"}).json()["allowed"] is False
assert c.post("/tool/patient_status", json={"pathway_code": "PW-D1", "birth_year": "1959"}).json()["next_step"] == "Colonoscopy"
# sop
assert c.post("/tool/sop_lookup", json={"situation": "abnormal result with no follow up"}).json()["found"]
assert c.post("/tool/sop_lookup", json={"situation": "what dose of drug X"}).json()["found"] is False

# post-call payload (shape as ElevenLabs sends: data.analysis.data_collection_results.<id>.value)
def dc(**kw): return {k: {"value": v} for k, v in kw.items()}
payload = {"type": "post_call_transcription", "data": {"conversation_id": "conv_abc12345678",
  "analysis": {"data_collection_results": dc(caller_type="patient", language="ar", symptom_onset_date="2026-10-20",
      contacts_so_far=2, red_flags_mentioned="blood in stool", worry_0_10=7, knows_next_step=False,
      wants_callback=True, pathway_code="PW-D1", caller_confirmed_summary=True, call_summary="Worried about bleeding.")}}}
r = c.post("/post-call", json=payload).json()
assert r["pathway_id"] == "PW-D1" and r["needs_check"] is False, r
types = [e["type"] for e in store.events_for("PW-D1")]
assert all(t in types for t in ["pulse:PU1", "pulse:PU2", "pulse:PU4", "pulse:PU7", "suspicion_suggested"]), types
assert not any(t in types for t in ("S0", "PU6", "pulse:PU6")), types
onset = next(e for e in store.events_for("PW-D1") if e["type"] == "pulse:PU1")
assert onset["value"] == "w2_4" and onset["unit"] == "first_contact", onset
assert all(e["source"] == "elevenlabs-voice" and e["entered_by"] == "voice-agent"
           for e in store.events_for("PW-D1") if e["type"].startswith("pulse:")), store.events_for("PW-D1")
assert types.count("T0") == 1, "voice must not add a T0 event"
kinds = sorted(t["kind"] for t in store.pending_tasks(assigned_to="Laura"))
assert kinds == ["callback", "triage_review"], kinds
# missing onset -> needs check
p2 = {"data": {"conversation_id": "conv_zzz99999999", "analysis": {"data_collection_results": dc(caller_type="relative", worry_0_10=3)}}}
assert c.post("/post-call", json=p2).json()["needs_check"] is True
# signature enforcement
service.WEBHOOK_SECRET = "s3cret"
assert c.post("/post-call", json=payload).status_code == 401
import hmac, hashlib, time
body = json.dumps(payload).encode(); t = str(int(time.time()))
sig = f"t={t},v0=" + hmac.new(b"s3cret", f"{t}.".encode() + body, hashlib.sha256).hexdigest()
assert c.post("/post-call", content=body, headers={"ElevenLabs-Signature": sig, "content-type": "application/json"}).status_code == 200
assert c.get("/health").json() == {"ok": True}
service.SESSIONS["expired-test-token"] = ("L-1042", "coordinator", time.time() - 1)
expired = c.post("/tool/patient_status", json={"pathway_code": "PW-D1", "session_token": "expired-test-token"}).json()
assert expired["allowed"] is False and "expired" in expired["message"].lower()
assert not store.db.query("select type from events where pathway_id=? and type in ('S0','PU6','pulse:PU6')", ("PW-D1",))
assert store.db.query("select conversation_id from voice_call where conversation_id=?", ("conv_abc12345678",))
assert store.db.query("select kind from task where kind='callback'")
assert store.db.query("select action from access_log where action='verify'")

# Mounted app integration: use a separate temporary SQLite fallback so the live demo DB stays untouched.
api_db = "/tmp/voice_api_test.db"
if os.path.exists(api_db): os.remove(api_db)
os.environ["HV_SIM"] = "0"
import app.store as app_store
app_store.LOCAL = pathlib.Path(api_db)
from voice import service as mounted_service
mounted_service.WEBHOOK_SECRET = ""
mounted_service.DEMO_OPEN = True
from api.main import app as main_app, S
with TestClient(main_app) as main:
    assert main.get("/").status_code == 200
    assert main.get("/today.js").status_code == 200
    assert "elevenlabs-convai" in main.get("/mypath.js").text
    assert "wrow task" in main.get("/today.js").text
    assert ".wrow:not(.task)" in main.get("/app.js").text
    integrated = dict(payload)
    integrated["data"] = dict(payload["data"])
    integrated["data"]["conversation_id"] = "conv_today_12345678"
    integrated["data"]["analysis"] = dict(payload["data"]["analysis"])
    integrated["data"]["analysis"]["data_collection_results"] = dc(
        caller_type="patient", language="ar", symptom_onset_date="2026-10-20", contacts_so_far=2,
        red_flags_mentioned="blood in stool", worry_0_10=6, knows_next_step=False,
        pathway_code="PW-D1", caller_confirmed_summary=True, call_summary="Patient asked for a callback.")
    webhook = main.post("/voice/post-call", json=integrated)
    assert webhook.status_code == 200, webhook.text
    assert webhook.json()["pathway_id"] == "PW-D1"
    events = main.get("/api/events", params={"pathway_id": "PW-D1"}).json()["events"]
    assert any(e["type"] == "pulse:PU7" and e["value"] == "6" for e in events)
    assert not any(e["type"] in ("S0", "PU6", "pulse:PU6") for e in events)
    stored_call = S["store"].db.query("select language, raw from voice_call where conversation_id=?", ("conv_today_12345678",))[0]
    assert stored_call[0] == "ar", stored_call
    today = main.get("/api/worklist", params={"coordinator": "Laura"}).json()
    assert {t["kind"] for t in today["tasks"]} >= {"callback", "triage_review"}, today["tasks"]
    task_id = next(t["id"] for t in today["tasks"] if t["kind"] == "callback")
    assert main.post(f"/api/tasks/{task_id}/done", json={}).json()["done"] is True
    assert task_id not in {t["id"] for t in main.get("/api/worklist", params={"coordinator": "Laura"}).json()["tasks"]}
    assert main.get("/api/mypath/PW-D1").status_code == 200
    eq = main.get("/api/controltower").json()
    assert eq["synthetic"] and eq["pulse_equity"]["synthetic"]
    assert all("pathway_id" not in row for row in eq["pulse_equity"]["rows"])
    # The question endpoint reuses the canonical moment and localized Pulse dictionary.
    questions = main.post("/voice/tool/pulse_questions", json={"moment": "suspicion", "language": "fi"}).json()
    assert [x["item"] for x in questions["items"]] == ["PU4", "PU7"]
    assert questions["items"][0]["question"] == "Tiedätkö, mitä seuraavaksi tapahtuu?"
    # Source-backed journey guide is served for the pathway stage and via the voice webhook tool.
    guide = main.get("/api/mypath/PW-D1/journey-guide?lang=fi").json()
    assert guide["stage"] == "suspicion" and len(guide["myths"]) == 3 and guide["review_status"] == "example text, not clinically reviewed"
    spoken = main.post("/voice/tool/journey_guide", json={"pathway_id": "PW-D1", "language": "en"}).json()
    assert spoken["stage"] == "suspicion" and spoken["spoken_text"] and spoken["source_url"].startswith("https://")
    # Translate through the existing chain when available; no external model/API is called by this test.
    journey_guide.TRANSLATION_CACHE.clear()
    original_llm = journey_guide.llm.llm
    journey_guide.llm.llm = lambda *a, **k: (json.dumps({"what_is_happening": "Exempeltext", "today_you_can": "I dag",
        "ask_these": ["Fråga"], "who_to_call": "Koordinator", "myths": [{"myth": "Myt", "fact": "Fakta"}]}, ensure_ascii=False), "Test fake")
    translated = main.get("/api/mypath/PW-D1/journey-guide?lang=sv").json()
    assert translated["translation_engine"] == "Test fake" and translated["what_is_happening"] == "Exempeltext"
    assert translated["translation_label"] == "machine translated, needs human check"
    journey_guide.TRANSLATION_CACHE.clear()
    journey_guide.llm.llm = lambda *a, **k: (None, "offline")
    fallback = main.get("/api/mypath/PW-D1/journey-guide?lang=ar").json()
    assert fallback["language"] == "en" and "English example shown" in fallback["translation_label"]
    journey_guide.llm.llm = original_llm
    # A synthetic post-call represents a confirmed phone Pulse. No ElevenLabs call or credits used.
    phone_pulse = {"data": {"conversation_id": "conv_phone_pulse_123", "analysis": {"data_collection_results": dc(
        caller_type="patient", pathway_id="PW-D1", moment="suspicion", language="fi", pulse_answer_1="no",
        pulse_answer_2="7", call_summary="Synthetic phone Pulse sample.")}}}
    pulse_result = main.post("/voice/post-call", json=phone_pulse)
    assert pulse_result.status_code == 200, pulse_result.text
    pulse_events = main.get("/api/events", params={"pathway_id": "PW-D1"}).json()["events"]
    phone_event = next(e for e in reversed(pulse_events) if e["type"] == "pulse:PU7")
    assert phone_event["value"] == "7" and phone_event["source"] == "pulse:phone", phone_event
    assert {t["kind"] for t in main.get("/api/worklist", params={"coordinator": "Laura"}).json()["tasks"]} >= {"callback"}
    outbound = main.post("/voice/outbound", json={"pathway_id": "PW-D1", "moment": "suspicion"}).json()
    assert outbound["dry_run"] and outbound["call_placed"] is False
    eq2 = main.get("/api/controltower").json()["pulse_equity"]
    assert eq2["phone_share_pct"] is None and eq2["phone_share_suppressed"] is True
    tower = main.get("/api/controltower").json()
    assert tower["voice_metrics"]["calls_week"] >= 2 and tower["voice_metrics"]["pu4_no"] >= 1
    # V2b acceptance: confirmed phone worry reaches the shared engine, dashboard, and coordinator task list.
    before_kpis = main.get("/api/controltower").json()["kpis"]
    worry8 = {"data": {"conversation_id": "conv_v2b_worry8", "analysis": {"data_collection_results": dc(
        caller_type="patient", pathway_code="PW-D3", language="fi", worry_0_10=8,
        knows_next_step=True, caller_confirmed_summary=True, call_summary="Synthetic worry 8 test.")}}}
    worry_result = main.post("/voice/post-call", json=worry8)
    assert worry_result.status_code == 200, worry_result.text
    detail = main.get("/api/pathways/PW-D3").json()
    assert any("Worry 8 of 10" in str(alert) for alert in detail["alerts"]), detail["alerts"]
    worry_events = [e for e in S["store"].events_for("PW-D3") if e["type"] == "pulse:PU7"]
    assert worry_events and worry_events[-1]["value"] == "8" and worry_events[-1]["unit"] == "suspicion", worry_events
    assert worry_events[-1]["source"] == "elevenlabs-voice" and worry_events[-1]["entered_by"] == "voice-agent", worry_events[-1]
    assert any(t["kind"] == "callback" and t["pathway_id"] == "PW-D3"
               for t in main.get("/api/worklist", params={"coordinator": "Laura"}).json()["tasks"])
    after_kpis = main.get("/api/controltower").json()["kpis"]
    assert after_kpis["distress_pct"] != before_kpis["distress_pct"] or after_kpis["n_pu7"] != before_kpis["n_pu7"], (before_kpis, after_kpis)
    # Missing configuration must fail closed on the mounted live routes.
    saved_live_auth = mounted_service.TOOL_SECRET, mounted_service.WEBHOOK_SECRET
    mounted_service.TOOL_SECRET, mounted_service.WEBHOOK_SECRET, mounted_service.DEMO_OPEN = "", "", False
    no_tool_auth = main.post("/voice/tool/sop_lookup", json={"situation": "result"})
    assert no_tool_auth.status_code == 503, (no_tool_auth.status_code, no_tool_auth.text)
    no_webhook_auth = main.post("/voice/post-call", json=worry8)
    assert no_webhook_auth.status_code == 503, (no_webhook_auth.status_code, no_webhook_auth.text)
    mounted_service.TOOL_SECRET, mounted_service.WEBHOOK_SECRET, mounted_service.DEMO_OPEN = *saved_live_auth, True
    # A clinician suggestion appears in triage, and only the button's action writes T0.
    S["store"].add_pathway(dict(id="PW-V4-1", name="Demo patient", age=55, sex="f", language="fi",
                                 county="Länsi-Uusimaa", cancer="colorectal", onset_days=4, interpreter=False))
    S["store"].append("PW-V4-1", "suspicion_suggested", S["store"].vnow, "blood in stool; synthetic test")
    call_data = main.get("/api/calls", params={"county": "Länsi-Uusimaa"}).json()
    suggestion = next(x for x in call_data["suggestions"] if x["id"] == "PW-V4-1")
    assert suggestion["says"] == "blood in stool; synthetic test"
    started = main.post("/api/fasttrack/suggested", json={"pathway_id": "PW-V4-1", "flag": "Rectal bleeding", "nurse": "Petra"})
    assert started.status_code == 200, started.text
    assert any(e["type"] == "T0" and e["entered_by"] == "nurse:Petra" for e in S["store"].events_for("PW-V4-1"))
    # Drafting alone writes no patient message; a coordinator approval does.
    import api.main as api_module
    original_draft = api_module.messages.draft
    api_module.messages.draft = lambda *a, **k: {"pathway_id": "PW-D1", "text_en": "Synthetic draft", "text_local": "Synthetic draft"}
    before_msgs = sum(e["type"] == "message" for e in S["store"].events_for("PW-D1"))
    assert main.post("/api/messages/draft", json={"pathway_id": "PW-D1"}).status_code == 200
    assert sum(e["type"] == "message" for e in S["store"].events_for("PW-D1")) == before_msgs
    api_module.messages.draft = original_draft
    booking = {"step": "T3", "due": "2026-11-16T10:00:00Z", "label": "Colonoscopy", "when": "Monday 10:00", "slot": None}
    approved = main.post("/api/messages/approve", json={"pathway_id": "PW-D1", "text": "Synthetic approved message", "text_en": "Synthetic approved message",
        "language": "ar", "coordinator": "Laura", "booking": booking})
    assert approved.status_code == 200 and any(e["type"] == "message" for e in S["store"].events_for("PW-D1"))
    # Runtime guard across a red-flag post-call path; T0 remains a clinician action.
    original_append = EventStore.append
    def no_voice_t0(self, pid, typ, *args, **kwargs):
        assert typ != "T0", "voice attempted to write T0"
        return original_append(self, pid, typ, *args, **kwargs)
    EventStore.append = no_voice_t0
    try:
        guarded = main.post("/voice/post-call", json={"data": {"conversation_id": "conv_guard_no_t0", "analysis": {"data_collection_results": dc(
            caller_type="patient", pathway_id="PW-V4-1", red_flags_mentioned="synthetic symptom", call_summary="Synthetic only.")}}})
        assert guarded.status_code == 200
    finally:
        EventStore.append = original_append
    national = main.get("/api/national").json()
    assert national["synthetic"] and "PW-D1" not in json.dumps(national)
    assert all((r["gap"] is None) if r["n"] < 5 else True for r in main.get("/api/controltower").json()["equity"]["rows"])

# Tool auth hardening: no secret is permitted only in explicit demo mode; configured secrets always validate.
saved_secret, saved_demo, saved_webhook = service.TOOL_SECRET, service.DEMO_OPEN, service.WEBHOOK_SECRET
service.TOOL_SECRET, service.WEBHOOK_SECRET, service.DEMO_OPEN = "", "", False
assert c.post("/tool/sop_lookup", json={"situation": "result"}).status_code == 503
assert c.post("/post-call", json=payload).status_code == 503
service.DEMO_OPEN = True
assert c.post("/tool/sop_lookup", json={"situation": "result"}).status_code == 200
service.DEMO_OPEN = False
service.TOOL_SECRET, service.WEBHOOK_SECRET = "test-secret", "test-webhook-secret"
assert c.post("/tool/sop_lookup", json={"situation": "result"}).status_code == 401
assert c.post("/tool/sop_lookup", json={"situation": "result"}, headers={"x-tool-secret": "test-secret"}).status_code == 200
service.TOOL_SECRET, service.WEBHOOK_SECRET, service.DEMO_OPEN = saved_secret, saved_webhook, saved_demo

# Bounded rate limiter: exact limit succeeds, next request is rejected without invoking the tool.
saved_limit, saved_window = service.RATE_LIMIT_REQUESTS, service.RATE_LIMIT_WINDOW_SECONDS
service.RATE_LIMIT_REQUESTS, service.RATE_LIMIT_WINDOW_SECONDS = 2, 60
service.RATE_BUCKETS.clear()
assert c.post("/tool/sop_lookup", json={"situation": "result"}).status_code == 200
assert c.post("/tool/sop_lookup", json={"situation": "result"}).status_code == 200
assert c.post("/tool/sop_lookup", json={"situation": "result"}).status_code == 429
service.RATE_LIMIT_REQUESTS, service.RATE_LIMIT_WINDOW_SECONDS = saved_limit, saved_window

# Access log schema contains only audit identifiers/actions; it stores no caller text or patient name.
access_columns = [r[1] for r in store.db.query("pragma table_info(access_log)")]
assert "summary" not in access_columns and "transcript" not in access_columns and "name" not in access_columns
access_rows = str(store.db.query("select * from access_log"))
assert "Amina H." not in access_rows and "Worried about bleeding" not in access_rows

print("all voice tests passed; shared SQLite store, Today tasks and dashboard integration verified")
