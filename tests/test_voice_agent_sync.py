"""Offline checks for the redacted, explicitly gated agent sync script."""
import io
import json
import unittest
from unittest.mock import Mock

from voice import agent_config, create_agent


class VoiceAgentSyncTests(unittest.TestCase):
    def test_desired_config_contains_end_call_and_timeout_limits(self):
        cfg = agent_config.build("https://synthetic.invalid", "synthetic-tool-secret")
        cc = cfg["conversation_config"]
        self.assertIn("end_call", cc["agent"]["prompt"]["built_in_tools"])
        self.assertEqual(cc["turn"]["silence_end_call_timeout"], 20)
        self.assertEqual(cc["conversation"]["max_duration_seconds"], 300)
        self.assertEqual(set(cc["language_presets"]), {"ar", "fi", "hi", "no", "sv"})
        self.assertEqual([tool["name"] for tool in cc["agent"]["prompt"]["tools"]],
                         ["pulse_questions", "journey_guide", "verify_staff", "patient_status", "sop_lookup"])

    def test_dry_run_never_calls_api_or_prints_synthetic_secrets(self):
        output = io.StringIO()
        opener = Mock(side_effect=AssertionError("dry-run attempted a request"))
        result = create_agent.main(["--base-url", "https://synthetic.invalid", "--dry-run"],
            environ={"ELEVENLABS_API_KEY": "synthetic-api-secret", "VOICE_TOOL_SECRET": "synthetic-hook-secret"},
            urlopen=opener, stdout=output)
        self.assertEqual(result, 0)
        opener.assert_not_called()
        self.assertNotIn("synthetic-api-secret", output.getvalue())
        self.assertNotIn("synthetic-hook-secret", output.getvalue())
        self.assertIn("silence_end_call_timeout", output.getvalue())

    def test_write_requires_explicit_yes(self):
        output = io.StringIO()
        opener = Mock(side_effect=AssertionError("unconfirmed request attempted"))
        result = create_agent.main(["--base-url", "https://synthetic.invalid", "--update", "synthetic-agent"],
            environ={"ELEVENLABS_API_KEY": "synthetic-api-secret", "VOICE_TOOL_SECRET": "synthetic-hook-secret"},
            urlopen=opener, stdout=output)
        self.assertEqual(result, 0)
        opener.assert_not_called()
        self.assertIn("No API write made", output.getvalue())


if __name__ == "__main__":
    unittest.main()
