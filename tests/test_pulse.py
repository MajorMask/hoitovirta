"""Pulse schedule, validation, localization, and KPI checks with synthetic data."""
import os
import asyncio
import pathlib
import tempfile
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

os.environ["HV_FORCE_SQLITE"] = "1"
os.environ["HV_SIM"] = "0"
os.environ["HV_DEMO_OPEN"] = "1"
os.environ["HV_PERSONA_TOKEN_SECRET"] = "test-only-pulse-persona-secret"

from aggregate import kpis
from act import pulse_voice
from app import i18n
from app.store import DB
from engine import pulse
from engine import scopes
from store.events import EventStore


class PulseTests(unittest.TestCase):
    def test_nps_is_first_and_feedback_is_optional_in_both_moments(self):
        now = datetime(2026, 11, 14, tzinfo=timezone.utc)
        for moment in ("diagnosis", "treatment"):
            f = {"pulse": [], "ts": {"T4" if moment == "diagnosis" else "T6": now},
                 "messages": [], "handovers": [], "language": "en"}
            pending = pulse.pending(f, now)
            self.assertEqual(pending["items"][:2], ["PU9", "PU7" if moment == "diagnosis" else "PU8"])
            self.assertEqual(pending["items"][2], "PU9b")
            self.assertEqual(pending["optional"], ["PU9b"])

    def test_handover_has_gate_and_conditional_pu5(self):
        now = datetime(2026, 11, 14, tzinfo=timezone.utc)
        f = {"pulse": [], "ts": {}, "messages": [], "handovers": [(now, {})], "language": "en"}
        pending = pulse.pending(f, now)
        self.assertEqual(pending["items"], ["PU4", "PU5a"])
        self.assertEqual(pending["conditional"], {"PU5a": {"yes": "PU5"}})
        self.assertEqual(pulse.CODEBOOK["PU5a"][1], ["yes", "no", "not_tried"])
        self.assertTrue(pulse.valid("PU5a", "not_tried"))
        self.assertEqual(pulse_voice.map_answer("PU5a", "I haven't tried", "en")["value"], "not_tried")
        self.assertFalse(pulse.valid("PU5", "not_tried"))

    def test_optional_text_accepts_short_answer_or_skip(self):
        self.assertTrue(pulse.valid("PU9b", "The nurse explained the next step"))
        self.assertTrue(pulse.valid("PU9b", "skip"))
        self.assertFalse(pulse.valid("PU9b", "  "))
        self.assertFalse(pulse.valid("PU9b", "x" * 501))

    def test_requested_patient_strings_exist_in_en_fi_sv(self):
        expected = {
            "en": ("Did you try to reach your nurse?", "What most affected your experience?", "I haven't tried", "Skip"),
            "fi": ("Yrititkö tavoittaa hoitajasi?", "Mikä vaikutti kokemukseesi eniten?", "En ole yrittänyt", "Ohita"),
            "sv": ("Försökte du nå din sjuksköterska?", "Vad påverkade din upplevelse mest?", "Jag har inte försökt", "Hoppa över"),
        }
        for lang, strings in expected.items():
            translated, _ = i18n.get(lang)
            self.assertEqual(translated["q_PU5a"], strings[0])
            self.assertEqual(translated["q_PU9b"], strings[1])
            self.assertEqual(translated["opt_PU5a_not_tried"], strings[2])
            self.assertEqual(translated["opt_PU9b_skip"], strings[3])
            self.assertFalse(any(word in translated["pulse_title"].lower() for word in ("two", "kaksi", "två")))

    def test_api_accepts_optional_text_and_skip(self):
        from fastapi.testclient import TestClient
        from api import main
        tmp = tempfile.TemporaryDirectory(prefix="hv-pulse-api-")
        try:
            store = EventStore(DB(sqlite_path=pathlib.Path(tmp.name) / "events.db"))
            store.add_pathway(dict(id="PW-D1", name="Synthetic A.", age=51, sex="f", language="en",
                                   county="Länsi-Uusimaa", cancer="colorectal", onset_days=10, interpreter=False))
            store.vnow = datetime(2026, 11, 14, tzinfo=timezone.utc)
            main.S["store"] = store
            client = TestClient(main.app)
            headers = {"X-Persona-Token": scopes.issue_token("patient", "PW-D1", secret=os.environ["HV_PERSONA_TOKEN_SECRET"])}
            response = client.post("/api/pulse", json={"pathway_id": "PW-D1", "item": "PU9b",
                                                         "value": "A clear explanation helped", "moment": "diagnosis"}, headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            skipped = client.post("/api/pulse", json={"pathway_id": "PW-D1", "item": "PU9b",
                                                       "value": "skip", "moment": "diagnosis"}, headers=headers)
            self.assertEqual(skipped.status_code, 200, skipped.text)
        finally:
            tmp.cleanup()

    def test_voice_text_item_returns_transcript_for_patient_confirmation(self):
        from api import main
        tmp = tempfile.TemporaryDirectory(prefix="hv-pulse-voice-")
        try:
            store = EventStore(DB(sqlite_path=pathlib.Path(tmp.name) / "events.db"))
            store.add_pathway(dict(id="PW-D1", name="Synthetic A.", age=51, sex="f", language="en",
                                   county="Länsi-Uusimaa", cancer="colorectal", onset_days=10, interpreter=False))
            main.S["store"] = store
            request = SimpleNamespace(state=SimpleNamespace(persona_role="all", persona_token=None),
                                      headers={"content-type": "audio/webm"}, body=AsyncMock(return_value=b"synthetic audio"))
            with patch.object(main.voice, "available", return_value=True), patch.object(main.voice, "transcribe", return_value=("The nurse listened.", "fake")):
                result = asyncio.run(main.pulse_from_voice(request, "PW-D1", "PU9b", "en"))
            self.assertEqual(result["value"], "The nurse listened.")
            self.assertEqual(result["confidence"], 0.9)
        finally:
            tmp.cleanup()

    def test_reached_within_one_working_day_kpi_uses_answered_pu5(self):
        tmp = tempfile.TemporaryDirectory(prefix="hv-pulse-kpi-")
        try:
            store = EventStore(DB(sqlite_path=pathlib.Path(tmp.name) / "events.db"))
            now = datetime(2026, 11, 14, tzinfo=timezone.utc)
            for i in range(5):
                pid = f"PW-D{i+1}"
                store.add_pathway(dict(id=pid, name=f"Synthetic {i}", age=50+i, sex="f", language="en",
                                        county="Länsi-Uusimaa", cancer="colorectal", onset_days=10, interpreter=False))
                store.append(pid, "pulse:PU5", now, "yes" if i < 3 else "no", unit="handover:synthetic", source="pulse:app", entered_by="patient")
            out = kpis.kpis(store, county="Länsi-Uusimaa")
            self.assertEqual(out["reached_1wd_pct"], 60.0)
            self.assertEqual(out["n_pu5"], 5)
        finally:
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
