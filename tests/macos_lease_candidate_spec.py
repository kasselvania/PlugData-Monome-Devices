from __future__ import annotations

import pathlib
import re
import subprocess
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = PROJECT_ROOT / "tools" / "macos_serialosc_lease_candidate.sh"


class MacOSLeaseCandidateSpec(unittest.TestCase):
    def test_script_is_valid_bash_and_help_is_read_only(self) -> None:
        subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
        result = subprocess.run(
            ["bash", str(SCRIPT), "help"],
            check=True,
            text=True,
            capture_output=True,
        )
        self.assertIn("prepare [SOURCE_DIR]", result.stdout)
        self.assertIn("restore-stable", result.stdout)
        self.assertIn("never overwritten or deleted", result.stdout)

    def test_candidate_is_pinned_and_separate_from_stable(self) -> None:
        source = SCRIPT.read_text()

        def assignment(name: str) -> str:
            match = re.search(rf'^{name}="([^"]+)"$', source, re.MULTILINE)
            self.assertIsNotNone(match, name)
            return match.group(1)

        revision = assignment("FORK_REVISION")
        self.assertEqual(len(revision), 40)
        self.assertEqual(revision[:7], assignment("FORK_SHORT_REVISION"))
        self.assertNotEqual(
            assignment("STABLE_SERVICE_LABEL"),
            assignment("CANDIDATE_SERVICE_LABEL"),
        )
        self.assertIn("serialosc-lease-candidate", source)
        self.assertIn("verify_source", source)
        self.assertIn("verify_candidate_files", source)

    def test_activation_has_an_explicit_rollback_path(self) -> None:
        source = SCRIPT.read_text()
        activation = source[source.index("activate_candidate()") :]
        self.assertIn("Stable LaunchAgent is unavailable for rollback", activation)
        self.assertIn("restore_stable_service", activation)
        self.assertIn("Candidate activation failed", activation)
        self.assertIn("(verify_candidate_active) || return 1", source)


if __name__ == "__main__":
    unittest.main()
