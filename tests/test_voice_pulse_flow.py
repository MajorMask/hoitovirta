"""Synthetic ElevenLabs post-call fixture, matching the sanitized live data shape."""
import pathlib
import tempfile
import unittest

from fastapi.testclient import TestClient
from app.store import DB
from engine import safety
from store.events import EventStore
from voice import service


def result(value):
    return {"value": value}


def pulse_payload(conversation_id, *, symptom="", answer_1="no", answer_2="7"):
    fields = {
        "caller_type": "patient", "language": "fi", "symptom_summary": symptom,
        "symptom_onset_date": "", "contacts_so_far": None, "red_flags_mentioned": "",
        "worry_0_10": "", "knows_next_step": None, "wants_callback": False,
        "pathway_code": "PW-D1", "caller_confirmed_summary": True,
        "call_summary": "Synthetic phone Pulse test.", "pathway_id": "PW-D1",
        "moment": "suspicion", "pulse_answer_1": answer_1, "pulse_answer_2": answer_2,
    }
    return {"type": "post_call_transcription", "data": {"conversation_id": conversation_id,
            "analysis": {"data_collection_results": {k: result(v) for k, v in fields.items()}}}}


class VoicePulseFlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="hv-voice-pulse-")
        self.store = EventStore(DB(sqlite_path=pathlib.Path(self.tmp.name) / "voice.db"))
        self.store.add_pathway(dict(id="PW-D1", name="Synthetic A.", age=67, sex="f", language="fi",
                                    county="Länsi-Uusimaa", cancer="colorectal", onset_days=12, interpreter=False))
        from datetime import datetime, timezone
        self.store.append("PW-D1", "T0", datetime(2026, 11, 14, tzinfo=timezone.utc), "Synthetic test", source="test", entered_by="clinician")
        service.configure_store(self.store)
        service.TOOL_SECRET = ""
        service.WEBHOOK_SECRET = ""
        service.DEMO_OPEN = True
        service.POST_CALL_IDS.clear()
        self.client = TestClient(service.app)

    def tearDown(self):
        self.tmp.cleanup()

    def test_phone_pulse_items_channel_callback_and_duplicate_idempotency(self):
        payload = pulse_payload("conv_synthetic_pulse_once")
        first = self.client.post("/post-call", json=payload)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["pathway_id"], "PW-D1")
        events = [e for e in self.store.events_for("PW-D1") if e["type"] in ("pulse:PU4", "pulse:PU7")]
        self.assertEqual([(e["type"], e["value"]) for e in events], [("pulse:PU4", "no"), ("pulse:PU7", "7")])
        self.assertTrue(all(e["source"] == "pulse:phone" for e in events), events)
        self.assertEqual(self.store.pending_tasks(pathway_id="PW-D1")[0]["kind"], "callback")
        before = (len(events), len(self.store.pending_tasks(pathway_id="PW-D1")))
        second = self.client.post("/post-call", json=payload)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertTrue(second.json()["duplicate"])
        after_events = [e for e in self.store.events_for("PW-D1") if e["type"] in ("pulse:PU4", "pulse:PU7")]
        self.assertEqual(before, (len(after_events), len(self.store.pending_tasks(pathway_id="PW-D1"))))
        self.assertEqual(self.store.db.query("select count(*) from voice_call where conversation_id=?", ("conv_synthetic_pulse_once",))[0][0], 1)
        self.assertFalse(any(e["type"] == "T0" and e["entered_by"] == "voice-agent" for e in self.store.events_for("PW-D1")))

    def test_voice_review_uses_the_shared_urgent_phrase_list(self):
        self.assertTrue(safety.is_urgent("I suddenly have chest pain"))
        self.assertTrue(safety.is_urgent("Minulla on äkillinen sekavuus"))
        response = self.client.post("/post-call", json=pulse_payload("conv_urgent_synthetic", symptom="chest pain"))
        self.assertEqual(response.status_code, 200, response.text)
        tasks = self.store.pending_tasks(pathway_id="PW-D1")
        triage = next(t for t in tasks if t["kind"] == "triage_review")
        self.assertIn("URGENT SAFETY", triage["detail"])
        self.assertFalse(any(e["type"] == "T0" and e["entered_by"] == "voice-agent" for e in self.store.events_for("PW-D1")))


if __name__ == "__main__":
    unittest.main()
