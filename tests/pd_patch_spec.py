#!/usr/bin/env python3

from __future__ import annotations

import pathlib
import re
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
PATCHES = (
    "monome-session.pd",
    "monome-session-help.pd",
    "monome-session-smoke.pd",
    "monome-session-lease-smoke.pd",
    "monome-session-contention-smoke.pd",
    "monome-session-displacement-smoke.pd",
    "monome-grid.pd",
    "monome-grid-session.pd",
    "monome-grid-smoke.pd",
    "monome-grid-256-smoke.pd",
    "monome-grid-dual-smoke.pd",
    "monome-grid-live-slot.pd",
    "monome-grid-live.pd",
    "monome-grid-contender-live.pd",
    "monome-arc.pd",
    "monome-arc-session.pd",
    "monome-arc-smoke.pd",
    "monome-arc-live-slot.pd",
    "monome-arc-live.pd",
)
NODE = re.compile(r"^#X (?:obj|msg|text|floatatom|symbolatom|listbox) ")
CONNECT = re.compile(r"^#X connect (\d+) \d+ (\d+) \d+;$")
UNESCAPED_COMMA = re.compile(r"(?<!\\),")


class PdPatchTests(unittest.TestCase):
    def test_patch_connections_reference_existing_nodes(self) -> None:
        for filename in PATCHES:
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

    def test_patch_text_has_no_unescaped_message_commas(self) -> None:
        for filename in PATCHES:
            with self.subTest(filename=filename):
                for line in (PROJECT_ROOT / filename).read_text().splitlines():
                    if line.startswith("#X text "):
                        self.assertIsNone(UNESCAPED_COMMA.search(line), line)

    def test_grid_redraw_is_bounded_and_release_is_intercepted(self) -> None:
        grid_patch = (PROJECT_ROOT / "monome-grid.pd").read_text()
        self.assertIn("metro 16", grid_patch)
        self.assertIn("msg 700 135 flush", grid_patch)

        session_patch = (PROJECT_ROOT / "monome-grid-session.pd").read_text()
        self.assertIn("route release", session_patch)
        self.assertIn("prepare_release", session_patch)
        self.assertIn("monome-session \\$1 \\$2", session_patch)

    def test_arc_redraw_is_bounded_explicit_and_release_is_intercepted(self) -> None:
        arc_patch = (PROJECT_ROOT / "monome-arc.pd").read_text()
        self.assertIn("monome-arc-core \\$1", arc_patch)
        self.assertIn("metro 16", arc_patch)

        session_patch = (PROJECT_ROOT / "monome-arc-session.pd").read_text()
        self.assertIn("route release", session_patch)
        self.assertIn("prepare_release", session_patch)
        self.assertIn("monome-session \\$1 \\$2", session_patch)
        self.assertIn("monome-arc \\$3", session_patch)

    def test_arc_smoke_uses_an_explicit_four_ring_fake_device(self) -> None:
        smoke = (PROJECT_ROOT / "monome-arc-smoke.pd").read_text()
        self.assertIn("select a400 monome\\ arc\\ 4 17003", smoke)
        self.assertIn("monome-arc-session 17782 120 4", smoke)
        self.assertIn("led 3 63 10", smoke)

    def test_arc_live_workbench_is_explicit_and_separately_routed(self) -> None:
        live = (PROJECT_ROOT / "monome-arc-live.pd").read_text()
        slot = (PROJECT_ROOT / "monome-arc-live-slot.pd").read_text()
        self.assertEqual(live.count("else/popmenu"), 1)
        self.assertIn("monome-arc-live-slot 17782 4", live)
        self.assertIn("netreceive -u 17901", live)
        self.assertIn("route select session arc discovery", live)
        self.assertIn("monome-arc-session \\$1 120 \\$2", slot)
        self.assertIn("opts into leases", slot)
        self.assertIn("protocol lease", slot)
        self.assertIn("takeover", live)

    def test_capability_osc_enters_only_through_session_core(self) -> None:
        session_patch = (PROJECT_ROOT / "monome-session.pd").read_text()
        self.assertIn("list prepend device_osc", session_patch)
        self.assertEqual(session_patch.count("netsend -u -b"), 2)

    def test_live_workbench_has_loopback_control_inlet(self) -> None:
        live_patch = (PROJECT_ROOT / "monome-grid-live.pd").read_text()
        self.assertIn("netreceive -u 17900", live_patch)
        self.assertIn(
            "route a_select a_session a_grid b_select b_session b_grid discovery",
            live_patch,
        )

    def test_live_workbench_has_machine_readable_key_output(self) -> None:
        live_patch = (PROJECT_ROOT / "monome-grid-live.pd").read_text()
        self.assertIn("netsend -u", live_patch)
        self.assertIn("connect localhost 17910", live_patch)
        self.assertIn("list prepend a_key", live_patch)
        self.assertIn("list prepend b_key", live_patch)

    def test_contender_workbench_uses_isolated_ports(self) -> None:
        contender = (PROJECT_ROOT / "monome-grid-contender-live.pd").read_text()
        self.assertEqual(contender.count("else/popmenu"), 1)
        self.assertIn("monome-discovery 18779 12002 180", contender)
        self.assertIn("monome-grid-live-slot 18780", contender)
        self.assertIn("netreceive -u 18900", contender)
        self.assertIn("route a_select a_session a_grid discovery", contender)

    def test_live_workbench_uses_registry_backed_device_menus(self) -> None:
        live_patch = (PROJECT_ROOT / "monome-grid-live.pd").read_text()
        live_slot = (PROJECT_ROOT / "monome-grid-live-slot.pd").read_text()
        self.assertEqual(live_patch.count("else/popmenu"), 2)
        self.assertIn("Device menus are populated dynamically", live_patch)
        self.assertIn("menu protocol", live_slot)
        self.assertIn("protocol lease", live_slot)
        self.assertIn("takeover", live_patch)

    def test_session_transport_routes_lease_protocol_and_renewal_timer(self) -> None:
        session_patch = (PROJECT_ROOT / "monome-session.pd").read_text()
        for path in (
            "/sys/lease/state",
            "/sys/lease/granted",
            "/sys/lease/renewed",
            "/sys/lease/released",
            "/sys/lease/rejected",
            "/sys/lease/lost",
        ):
            self.assertIn(path, session_patch)
        self.assertIn("lease_timer cancel_lease_timer", session_patch)
        self.assertIn("list prepend lease_state", session_patch)

        smoke = (PROJECT_ROOT / "monome-session-lease-smoke.pd").read_text()
        self.assertIn("protocol lease", smoke)
        self.assertIn("monome-session 17780 120", smoke)

    def test_discovery_normalizes_remove_notification_to_serial(self) -> None:
        discovery_patch = (PROJECT_ROOT / "monome-discovery.pd").read_text()
        self.assertIn("list split 1", discovery_patch)


if __name__ == "__main__":
    unittest.main(verbosity=2)
