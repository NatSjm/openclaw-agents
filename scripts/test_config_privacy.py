"""Check that privacy failures are detected without revealing their values."""
import json
from pathlib import Path
import tempfile
import unittest

from check_config_privacy import find_issues, private_values


class ConfigPrivacyTests(unittest.TestCase):
    def test_private_metadata_and_credentials_are_detected_without_echoing_them(self):
        private = {"synthetic-private-token", "synthetic-session-label", "openai:private-profile"}
        data = {"gateway": {"token": "synthetic-private-token"},
                "model": "openai/synthetic-session-label",
                "auth": {"profiles": {"openai:private-profile": {"email": "person@example.invalid"}}}}
        issues = find_issues(json.dumps(data), private)
        self.assertEqual(len(issues), 4)
        for value in (*private, "person@example.invalid"):
            self.assertNotIn(value, "\n".join(issues))

    def test_environment_references_are_accepted(self):
        data = {"gateway": {"auth": {"token": {"source": "env", "provider": "default",
                                                "id": "OPENCLAW_GATEWAY_TOKEN"}}},
                "channels": {"a2a": {"peers": {"homework-client": {"token": "${A2A_CLIENT_TOKEN}"}}}},
                "agents": {"entries": {"main": {"workspace": "/project/openclaw/workspace"}}}}
        self.assertEqual(find_issues(json.dumps(data), {"main", "synthetic-private-token"}), [])

    def test_private_values_come_from_the_private_env_file(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / ".local").mkdir()
            (project / ".local/openclaw.env").write_text(
                "OPENAI_API_KEY=synthetic-api-key\nTELEGRAM_BOT_TOKEN='synthetic-bot-token'\nTZ=Europe/Kyiv\n")
            self.assertEqual(private_values(project), {"synthetic-api-key", "synthetic-bot-token"})

    def test_new_owner_identifier_is_detected_without_a_previous_env_value(self):
        text = '{"commands":{"ownerAllowFrom":["telegram:998877665"]}}'
        issues = find_issues(text, set())
        self.assertEqual(issues, ["Owner identifiers belong in private environment references."])
        self.assertNotIn("998877665", "\n".join(issues))

    def test_unrecognized_inline_credential_is_rejected(self):
        issues = find_issues('{"channels":{"telegram":{"botToken":"synthetic-new-credential"}}}', set())
        self.assertEqual(issues, ["An inline credential belongs in a private secret reference."])
        self.assertNotIn("synthetic-new-credential", "\n".join(issues))
