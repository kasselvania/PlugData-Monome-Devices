#!/usr/bin/env python3

from __future__ import annotations

import pathlib
import subprocess
import tempfile
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
PATCH_FILE = PROJECT_ROOT / "patches" / "serialosc-null-port.patch"
INSTALLER = PROJECT_ROOT / "tools" / "install_macos_serialosc.sh"


class MacOSSerialOSCTests(unittest.TestCase):
    def test_patch_is_limited_to_the_two_null_port_paths(self) -> None:
        patch = PATCH_FILE.read_text()
        targets = [
            line.removeprefix("diff --git a/").split(" b/", 1)[0]
            for line in patch.splitlines()
            if line.startswith("diff --git a/")
        ]
        self.assertEqual(
            targets,
            [
                "src/serialosc-device/config.c",
                "src/serialosc-device/osc/sys_methods.c",
            ],
        )
        self.assertIn("p ? strtol(p, NULL, 10) : 0", patch)
        self.assertIn("return port ? atoi(port) : 0", patch)
        self.assertNotIn("diagnostic", patch)
        self.assertNotIn("event_loop/select.c", patch)
        self.assertNotIn("src/serialoscd/uv.c", patch)
        self.assertNotIn("wscript", patch)

    def test_patch_applies_to_the_vulnerable_source_fragments(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            config = root / "src" / "serialosc-device" / "config.c"
            methods = root / "src" / "serialosc-device" / "osc" / "sys_methods.c"
            config.parent.mkdir(parents=True)
            methods.parent.mkdir(parents=True)
            config_lines = ["/* fixture */"] * 160
            config_lines[151] = '\tcfg_setint(sec, "port", strtol(p , NULL, 10));'
            config.write_text("\n".join(config_lines) + "\n")
            method_lines = ["/* fixture */"] * 110
            method_lines[97] = (
                'DECLARE_INFO_PROP(port, "i", '
                "atoi(lo_address_get_port(state->outgoing)))"
            )
            methods.write_text("\n".join(method_lines) + "\n")

            result = subprocess.run(
                ["patch", "--quiet", "-p1", "-i", str(PATCH_FILE)],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("p ? strtol(p, NULL, 10) : 0", config.read_text())
            self.assertIn("address_port(state->outgoing)", methods.read_text())

    def test_installer_shell_syntax_and_pinned_revision(self) -> None:
        result = subprocess.run(
            ["/bin/bash", "-n", str(INSTALLER)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        installer = INSTALLER.read_text()
        self.assertIn(
            'SERIALOSC_REVISION="ff53885cb227546d0f29f42f223ecf7a984df0e9"',
            installer,
        )
        self.assertIn("brew services stop serialosc", installer)
        self.assertIn("Expected one owner of UDP port", installer)
        self.assertIn("restore-homebrew", installer)


if __name__ == "__main__":
    unittest.main(verbosity=2)
