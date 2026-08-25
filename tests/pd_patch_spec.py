#!/usr/bin/env python3

from __future__ import annotations

import pathlib
import re
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SESSION_PATCHES = (
    "monome-session.pd",
    "monome-session-help.pd",
    "monome-session-smoke.pd",
    "monome-session-contention-smoke.pd",
    "monome-session-displacement-smoke.pd",
)
NODE = re.compile(r"^#X (?:obj|msg|text|floatatom|symbolatom|listbox) ")
CONNECT = re.compile(r"^#X connect (\d+) \d+ (\d+) \d+;$")
UNESCAPED_COMMA = re.compile(r"(?<!\\),")


class PdPatchTests(unittest.TestCase):
    def test_session_patch_connections_reference_existing_nodes(self) -> None:
        for filename in SESSION_PATCHES:
            with self.subTest(filename=filename):
                lines = (PROJECT_ROOT / filename).read_text().splitlines()
                node_count = sum(bool(NODE.match(line)) for line in lines)
                connections = [
                    CONNECT.match(line)
                    for line in lines
                    if line.startswith("#X connect ")
                ]
                self.assertGreater(node_count, 0)
                self.assertTrue(connections)
                self.assertNotIn(None, connections)
                for connection in connections:
                    assert connection is not None
                    source, destination = map(int, connection.groups())
                    self.assertLess(source, node_count)
                    self.assertLess(destination, node_count)

    def test_session_patch_text_has_no_unescaped_message_commas(self) -> None:
        for filename in SESSION_PATCHES:
            with self.subTest(filename=filename):
                for line in (PROJECT_ROOT / filename).read_text().splitlines():
                    if line.startswith("#X text "):
                        self.assertIsNone(UNESCAPED_COMMA.search(line), line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
