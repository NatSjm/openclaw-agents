"""Exercise publication boundaries with synthetic Git repositories."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from check_publication import inspect_text, history_findings


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.project = Path(self.scratch.name) / "source"
        self.project.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Template Author")
        self.git("config", "user.email", "template@example.invalid")

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.project), *args], stderr=subprocess.DEVNULL)

    def test_removed_private_text_is_detected_in_history(self):
        path = self.project / "notes.md"
        path.write_text("A synthetic-private-account value.\n")
        self.git("add", "notes.md")
        self.git("commit", "-qm", "Initial fixture")
        path.write_text("Generic instructions.\n")
        self.git("add", "notes.md")
        self.git("commit", "-qm", "Generic fixture")
        findings = history_findings(self.project, {"synthetic-private-account"})
        self.assertTrue(any("notes.md" in location for location, _ in findings))
        self.assertNotIn("synthetic-private-account", repr(findings))

    def test_private_paths_and_new_credentials_fail_without_echoing_values(self):
        self.assertIn("private runtime file", inspect_text(".local/state.json", "{}", set()))
        value = "ghp_" + "x" * 36
        issues = inspect_text("notes.md", value, set())
        self.assertIn("credential-shaped value", issues)
        self.assertNotIn(value, repr(issues))


if __name__ == "__main__":
    unittest.main()
