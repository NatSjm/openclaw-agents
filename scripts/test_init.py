"""Tests for docker/init.py: config install is repeatable and keeps runtime state."""
import json
from pathlib import Path
import sys
import unittest

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "docker"))
from init import build_config  # noqa: E402

TRACKED = json.loads((PROJECT / "config/openclaw.json").read_text(encoding="utf-8"))
FULL_ENV = {"TELEGRAM_BOT_TOKEN": "x", "A2A_CLIENT_TOKEN": "y"}


class InitTests(unittest.TestCase):
    def test_team_has_three_agents_with_different_tool_boundaries(self):
        entries = TRACKED["agents"]["entries"]
        self.assertEqual(set(entries), {"main", "researcher", "writer"})
        # Spawned children inherit the parent's tool policy: a web deny on the
        # Coordinator would strip web tools from the Researcher it delegates to.
        self.assertNotIn("tools", entries["main"])
        self.assertEqual(TRACKED["tools"]["web"]["search"]["provider"], "parallel-free")
        self.assertIn("group:web", entries["writer"]["tools"]["deny"])
        self.assertNotIn("group:web", entries["researcher"]["tools"]["deny"])
        self.assertIn("sessions_spawn", entries["researcher"]["tools"]["deny"])
        self.assertIn("sessions_spawn", entries["writer"]["tools"]["deny"])
        # Global deny always wins, so web must not be denied globally.
        self.assertNotIn("group:web", TRACKED["tools"]["deny"])

    def test_tracing_telegram_and_a2a_are_configured(self):
        self.assertTrue(TRACKED["diagnostics"]["otel"]["enabled"])
        self.assertTrue(TRACKED["plugins"]["entries"]["diagnostics-otel"]["enabled"])
        self.assertEqual(TRACKED["channels"]["a2a"]["peers"]["homework-client"]["token"], "${A2A_CLIENT_TOKEN}")
        bound = {(b["match"]["channel"], b["agentId"]) for b in TRACKED["bindings"]}
        self.assertEqual(bound, {("telegram", "main"), ("a2a", "researcher")})

    def test_runtime_state_is_preserved_and_tracked_settings_win(self):
        live = {"auth": {"order": {"openai": ["openai:manual"]}},
                "commands": {"ownerAllowFrom": ["telegram:1"]},
                "tools": {"deny": []}}
        data = build_config(TRACKED, live, FULL_ENV)
        self.assertEqual(data["auth"], live["auth"])
        self.assertEqual(data["commands"], live["commands"])
        self.assertEqual(data["tools"], TRACKED["tools"])

    def test_channels_without_tokens_are_disabled_and_tracked_input_is_untouched(self):
        data = build_config(TRACKED, {}, {})
        self.assertFalse(data["channels"]["telegram"]["enabled"])
        self.assertFalse(data["channels"]["a2a"]["enabled"])
        self.assertTrue(TRACKED["channels"]["telegram"]["enabled"])
        self.assertTrue(build_config(TRACKED, {}, FULL_ENV)["channels"]["telegram"]["enabled"])


if __name__ == "__main__":
    unittest.main()
