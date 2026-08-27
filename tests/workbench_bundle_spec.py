import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools" / "build_workbench_bundle.sh"


class WorkbenchBundleSpec(unittest.TestCase):
    def test_bundle_has_one_versioned_root_and_required_workbench_files(self):
        bundle_ref = os.environ.get("WORKBENCH_BUNDLE_REF", "HEAD")
        object_id = subprocess.check_output(
            ["git", "-C", str(ROOT), "rev-parse", "--verify", f"{bundle_ref}^{{object}}"],
            text=True,
        ).strip()
        prefix = f"plugdata-monome-workbench-{object_id[:12]}"

        with tempfile.TemporaryDirectory() as output_dir:
            result = subprocess.run(
                [str(BUILDER), "--ref", bundle_ref, "--output", output_dir],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("WORKBENCH BUNDLE PASSED", result.stdout)

            archive = Path(output_dir) / f"{prefix}.zip"
            checksum = archive.with_suffix(".zip.sha256")
            self.assertTrue(archive.is_file())
            self.assertTrue(checksum.is_file())

            expected_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            self.assertEqual(checksum.read_text().split()[0], expected_digest)

            with zipfile.ZipFile(archive) as bundle:
                names = set(bundle.namelist())

            required = {
                "README.md",
                "docs/DESIGN.md",
                "docs/LEASE-WORKBENCH.md",
                "docs/PROJECT-MAP.md",
                "docs/PLUGDATA-BITWIG-AB.md",
                "docs/WORKBENCH-BUNDLE.md",
                "monome-discovery.pd",
                "monome-session.pd",
                "monome_session.lua",
                "monome-grid.pd",
                "monome_grid.lua",
                "monome-arc.pd",
                "monome_arc.lua",
                "tools/fake_serialosc.py",
                "tools/build_workbench_bundle.sh",
                "tests/session_spec.lua",
                "tests/workbench_bundle_spec.py",
                "patches/serialosc-null-port.patch",
            }
            for relative_path in required:
                self.assertIn(f"{prefix}/{relative_path}", names)

            self.assertFalse(any("/.git/" in name for name in names))
            self.assertFalse(any("/__pycache__/" in name for name in names))
            self.assertTrue(all(name.startswith(f"{prefix}/") for name in names))


if __name__ == "__main__":
    unittest.main()
