"""Synthetic contract tests for the isolated Pulse sidecar."""
import unittest
from fastapi.testclient import TestClient

from pulse_service import main


class PulseServiceTests(unittest.TestCase):
    def setUp(self):
        with main._lock:
            main._responses.clear()
            main._tasks.clear()
        self.client = TestClient(main.app)

    def submit(self, moment, answers, *, language="fi"):
        return self.client.post("/api/responses", json={
            "demo_case": "DEMO-SYNTHETIC-1", "language": language,
            "moment": moment, "channel": "app", "answers": answers,
        })

    def test_instrument_has_documented_moments_and_sources(self):
        response = self.client.get("/api/instrument?language=fi")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["moments"], main.MOMENT_ITEMS)
        self.assertTrue(data["distress_source"].startswith("https://"))
        self.assertEqual(data["distress_cutoff"], 4)
        self.assertTrue(data["synthetic"])

    def test_first_contact_collects_patient_reported_onset_and_contact_count(self):
        result = self.submit("first_contact", {"PU1": "w2_4", "PU2": "3p"})
        self.assertEqual(result.status_code, 200, result.text)
        answers = result.json()["response"]["answers"]
        self.assertEqual(answers, {"PU1": "w2_4", "PU2": "3p"})
        self.assertEqual(result.json()["response"]["moment"], "first_contact")

    def test_handover_pu5_is_conditional_and_not_tried_is_valid(self):
        no = self.submit("handover", {"PU4": "yes", "PU5a": "not_tried"})
        self.assertEqual(no.status_code, 200, no.text)
        invalid = self.submit("handover", {"PU4": "yes", "PU5a": "no", "PU5": "no"})
        self.assertEqual(invalid.status_code, 422)
        yes = self.submit("handover", {"PU4": "yes", "PU5a": "yes", "PU5": "no"})
        self.assertEqual(yes.status_code, 200, yes.text)
        self.assertIn("nurse_not_reached_within_1_working_day", yes.json()["response"]["signals"])

    def test_distress_answer_creates_synthetic_follow_up_and_no_t0(self):
        result = self.submit("suspicion", {"PU4": "unsure", "PU7": 6})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertTrue(result.json()["feedback"]["task_created"])
        self.assertEqual(result.json()["response"]["signals"], ["distress_follow_up", "clarify_next_step"])
        self.assertTrue(result.json()["response"]["synthetic"])
        self.assertTrue(all(e["item_code"] != "T0" for e in result.json()["response"]["items"]))

    def test_diagnosis_nps_then_optional_comment_can_be_skipped(self):
        result = self.submit("diagnosis", {"PU9": "8", "PU7": 2, "PU9b": "skip"})
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["response"]["answers"]["PU9b"], "skip")
        self.assertEqual(self.submit("diagnosis", {"PU9": "8", "PU7": 2, "PU9b": "x" * 501}).status_code, 422)

    def test_unknown_items_and_real_identifiers_are_rejected(self):
        self.assertEqual(self.submit("suspicion", {"PU4": "yes", "PU7": 2, "name": "Ada"}).status_code, 422)
        bad = self.client.post("/api/responses", json={"demo_case": "real-person", "moment": "suspicion", "answers": {"PU4": "yes", "PU7": 1}})
        self.assertEqual(bad.status_code, 422)

    def test_small_cell_suppression_remains_server_side(self):
        for _ in range(4):
            self.submit("suspicion", {"PU4": "yes", "PU7": 2})
        data = self.client.get("/api/feedback").json()
        self.assertTrue(data["suppressed"])
        self.assertIsNone(data["metrics"])
        self.submit("suspicion", {"PU4": "yes", "PU7": 2})
        data = self.client.get("/api/feedback").json()
        # PU4/PU7 are reportable at n=5, while unrelated item groups remain hidden.
        self.assertTrue(data["suppressed"])
        self.assertEqual(data["metrics"]["respondents"], 5)
        self.assertEqual(data["metrics"]["informed_respondents"], 5)
        self.assertIsNone(data["metrics"]["nps"])

    def test_nps_and_reached_nurse_metrics_use_their_own_denominators(self):
        for i in range(5):
            self.submit("diagnosis", {"PU9": str(9 if i < 3 else 5), "PU7": 1})
            self.submit("handover", {"PU4": "yes", "PU5a": "yes", "PU5": "yes" if i < 4 else "no"})
        metrics = self.client.get("/api/feedback").json()["metrics"]
        self.assertEqual(metrics["nps"], 20.0)  # 3 promoters, 2 passives, no detractors
        self.assertEqual(metrics["nps_respondents"], 5)
        self.assertEqual(metrics["reached_1wd_pct"], 80.0)
        self.assertEqual(metrics["reached_1wd_respondents"], 5)


if __name__ == "__main__":
    unittest.main()
