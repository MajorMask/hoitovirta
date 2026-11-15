"""Server-side persona token and field-scope regression tests (synthetic SQLite only)."""
import os
import pathlib
import tempfile
import unittest
from types import SimpleNamespace
from datetime import datetime, timezone

os.environ["HV_FORCE_SQLITE"] = "1"
os.environ["HV_SIM"] = "0"
os.environ["HV_DEMO_OPEN"] = "0"
os.environ["HV_PERSONA_TOKEN_SECRET"] = "test-only-persona-secret"

from fastapi.testclient import TestClient
from app.store import DB
from store.events import EventStore
from engine import scopes
from api import main


class ScopeTests(unittest.TestCase):
    def setUp(self):
        os.environ["HV_DEMO_OPEN"] = "0"   # other test modules set it to 1 at import; this suite needs the locked mode
        os.environ["HV_PERSONA_TOKEN_SECRET"] = "test-only-persona-secret"
        self.tmp = tempfile.TemporaryDirectory(prefix="hv-scopes-")
        self.store = EventStore(DB(sqlite_path=pathlib.Path(self.tmp.name) / "events.db"))
        now = datetime(2026, 11, 14, tzinfo=timezone.utc)
        for pid, name in (("PW-D1", "Amina H."), ("PW-D2", "Synthetic B.")):
            self.store.add_pathway(dict(id=pid, name=name, age=67, sex="f", language="en", county="Länsi-Uusimaa", cancer="colorectal", onset_days=12, interpreter=True))
            self.store.append(pid, "T0", now, "Positive FIT", source="triage", entered_by="nurse")
            self.store.append(pid, "coordinator", now, "Laura", source="fast-track", entered_by="nurse")
        main.S["store"] = self.store
        main.S["sim"] = SimpleNamespace(calls={"Länsi-Uusimaa": 0})
        self.client = TestClient(main.app)  # no context manager: do not run the app lifespan against the user's local DB

    def tearDown(self):
        self.tmp.cleanup()

    def token(self, role, pathway=None, now=None):
        return scopes.issue_token(role, pathway, secret=os.environ["HV_PERSONA_TOKEN_SECRET"], now=now)

    def test_every_role_has_allowed_and_forbidden_routes(self):
        pairs = {
            "all": ("/api/pathways", "/api/pathways"),
            "patient": ("/api/mypath/PW-D1", "/api/controltower"),
            "family": ("/api/mypath/PW-D1", "/api/mypath/PW-D1/thread"),
            "triage": ("/api/fasttrack", "/api/national"),
            "coordinator": ("/api/worklist", "/api/national"),
            "admin": ("/api/slots", "/api/pathways/PW-D1"),
            "diagnostics": ("/api/reports", "/api/controltower"),
            "specialist": ("/api/worklist", "/api/outreach/list"),
            "screening": ("/api/outreach/list", "/api/mypath/PW-D1"),
            "county": ("/api/controltower", "/api/pathways/PW-D1"),
            "national": ("/api/national", "/api/worklist"),
            "steward": ("/api/reports", "/api/pathways/PW-D1"),
        }
        for role, (yes, no) in pairs.items():
            with self.subTest(role=role):
                self.assertTrue(scopes.allowed(role, scopes.category(yes)))
                if role != "all":
                    self.assertFalse(scopes.allowed(role, scopes.category(no)))

    def test_signed_token_is_bound_and_expires(self):
        token = self.token("patient", "PW-D1", now=100)
        self.assertEqual(scopes.verify_token(token, secret="test-only-persona-secret", now=101)["pathway_id"], "PW-D1")
        self.assertIsNone(scopes.verify_token(token, secret="wrong", now=101))
        self.assertIsNone(scopes.verify_token(token, secret="test-only-persona-secret", now=3700))
        self.assertFalse(scopes.pathway_matches(scopes.verify_token(token, secret="test-only-persona-secret", now=101), "/api/mypath/PW-D2"))

    def test_missing_or_forged_persona_is_refused_and_logged(self):
        self.assertEqual(self.client.get("/api/pathways").status_code, 401)
        self.assertEqual(self.client.get("/api/pathways", headers={"X-Persona-Token": "forged.value"}).status_code, 401)
        rows = self.store.db.query("select role, action, ok from access_log")
        self.assertGreaterEqual(len(rows), 2)
        self.assertTrue(all(row[2] == 0 for row in rows))

    def test_admin_direct_api_has_booking_fields_only(self):
        due = "2026-11-18T13:00:00+00:00"
        self.store.append("PW-D1", "booking", due, {"step": "T3", "due": due, "by": "Laura", "slot": "Läns-colonoscopy-20261118T1300"}, source="test", entered_by="test")
        token = self.token("admin")
        response = self.client.get("/api/worklist?coordinator=Laura", headers={"X-Persona-Token": token})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        for row in body["rows"]:
            self.assertFalse({"flag", "risk", "alerts", "open_loop", "cancer", "step", "pulse", "age"} & set(row))
            self.assertNotIn("Amina H.", row.get("name", ""))
        amina = next(row for row in body["rows"] if row["id"] == "PW-D1")
        self.assertEqual(set(amina["booking"]), {"due", "slot", "when", "reserved"})
        self.assertEqual(amina["slot"], amina["booking"]["slot"])
        self.assertTrue(amina["booking"]["reserved"])
        self.assertEqual(self.client.get("/api/pathways/PW-D1", headers={"X-Persona-Token": token}).status_code, 403)

    def test_scope_gaps_for_coordinator_diagnostics_and_steward(self):
        coordinator = {"X-Persona-Token": self.token("coordinator")}
        self.assertEqual(self.client.get("/api/calls?county=Länsi-Uusimaa", headers=coordinator).status_code, 200)
        self.assertEqual(self.client.get("/api/reports", headers=coordinator).status_code, 200)
        self.assertEqual(self.client.get("/api/worklist?coordinator=Laura", headers=coordinator).status_code, 200)
        self.assertEqual(self.client.get("/api/mypath/PW-D1", headers=coordinator).status_code, 200)
        diagnostics = {"X-Persona-Token": self.token("diagnostics")}
        self.assertEqual(self.client.get("/api/pathways/search?q=Amina", headers=diagnostics).status_code, 200)
        steward = {"X-Persona-Token": self.token("steward")}
        self.assertEqual(self.client.get("/api/pathways/search?q=Amina", headers=steward).status_code, 200)
        self.assertEqual(self.client.get("/api/rolemetrics?role=diagnostics", headers=steward).status_code, 200)

    def test_family_cannot_confirm_companion_need(self):
        family = {"X-Persona-Token": self.token("family", "PW-D1")}
        response = self.client.post("/api/mypath/PW-D1/companion/confirm", json={"need": "transport"}, headers=family)
        self.assertEqual(response.status_code, 403, response.text)

    def test_patient_notes_are_private_unless_shared(self):
        patient = {"X-Persona-Token": self.token("patient", "PW-D1")}
        self.assertEqual(self.client.post("/api/mypath/PW-D1/notes", json={"text": "private synthetic note"}, headers=patient).status_code, 200)
        self.assertEqual(self.client.post("/api/mypath/PW-D1/notes", json={"text": "shared synthetic note", "share": True}, headers=patient).status_code, 200)
        own = self.client.get("/api/mypath/PW-D1/notes", headers=patient).json()["notes"]
        self.assertEqual(len(own), 2)
        family = {"X-Persona-Token": self.token("family", "PW-D1")}
        shared = self.client.get("/api/mypath/PW-D1/notes", headers=family)
        self.assertEqual(shared.status_code, 200, shared.text)
        self.assertEqual([n["text"] for n in shared.json()["notes"]], ["shared synthetic note"])
        coordinator = {"X-Persona-Token": self.token("coordinator")}
        timeline = self.client.get("/api/pathways/PW-D1", headers=coordinator).json()
        self.assertNotIn("private synthetic note", str(timeline))
        events = self.client.get("/api/events?pathway_id=PW-D1", headers=coordinator).json()["events"]
        self.assertFalse(any(e["type"] == "patient_note" for e in events))

    def test_companion_skill_contract_and_proactive_moments(self):
        patient = {"X-Persona-Token": self.token("patient", "PW-D1")}
        response = self.client.post("/api/mypath/PW-D1/companion", json={"language": "en", "skill": "prepare"}, headers=patient)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["skill"], "prepare")
        self.assertEqual(body["cards"][0]["kind"], "checklist")
        self.assertIn("follow_ups", body)
        moments = self.client.get("/api/mypath/PW-D1/companion/moments?language=en", headers=patient)
        self.assertEqual(moments.status_code, 200, moments.text)
        self.assertLessEqual(len(moments.json()["cards"]), 2)

    def test_family_api_returns_only_own_next_step(self):
        token = self.token("family", "PW-D1")
        response = self.client.get("/api/mypath/PW-D1", headers={"X-Persona-Token": token})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(set(response.json()) - {"pathway_id", "first_name", "language", "place", "nurse", "next", "synthetic"}, set())
        self.assertEqual(self.client.get("/api/mypath/PW-D1/thread", headers={"X-Persona-Token": token}).status_code, 403)

    def test_patient_cannot_read_another_pathway_or_write_another_pulse(self):
        token = self.token("patient", "PW-D1")
        self.assertEqual(self.client.get("/api/mypath/PW-D2", headers={"X-Persona-Token": token}).status_code, 403)
        pulse = {"pathway_id": "PW-D2", "item": "PU7", "value": "6", "language": "en"}
        self.assertEqual(self.client.post("/api/pulse", json=pulse, headers={"X-Persona-Token": token}).status_code, 403)

    def test_under_five_aggregate_cells_are_suppressed_on_server(self):
        out = scopes.suppress_small_cells({"rows": [{"language": "ar", "n": 3, "dx_median": 12.0, "flagged": True}, {"language": "fi", "n": 7, "dx_median": 14.0}]})
        self.assertIsNone(out["rows"][0]["n"])
        self.assertIsNone(out["rows"][0]["dx_median"])
        self.assertTrue(out["rows"][0]["suppressed"])
        self.assertEqual(out["rows"][1]["n"], 7)


if __name__ == "__main__":
    unittest.main()
