#!/usr/bin/env python3

from __future__ import annotations

import pathlib
import socket
import sys
import threading
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from fake_serialosc import (  # noqa: E402
    Device,
    FakeSerialOSC,
    bind_callback,
    decode_message,
)
from live_serialosc_lease import (  # noqa: E402
    _send_test_pattern,
    expiry_test,
    lease_snapshot,
    renew_release_test,
)
from live_serialosc_state import DeviceState  # noqa: E402


def available_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as candidate:
        candidate.bind(("127.0.0.1", 0))
        return candidate.getsockname()[1]


class RunningSerialOSC:
    def __init__(self, devices: tuple[Device, ...] | None = None) -> None:
        if devices is None:
            devices = (
                Device(
                    "m100",
                    "monome 128",
                    available_udp_port(),
                    16,
                    8,
                ),
            )
        self.server = FakeSerialOSC(
            port=0,
            devices=devices,
            spawn_device_servers=True,
        )
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self.stopping.is_set():
            try:
                self.server.serve_once(0.01)
            except OSError:
                return

    def __enter__(self) -> FakeSerialOSC:
        self.thread.start()
        return self.server

    def __exit__(self, *_: object) -> None:
        self.stopping.set()
        self.server.close()
        self.thread.join(timeout=1)


class LiveSerialOSCLeaseTests(unittest.TestCase):
    def test_probe_reports_free_without_mutating_destination(self) -> None:
        with RunningSerialOSC() as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            entries = lease_snapshot(
                callback, (server.host, server.port), 0.5
            )
            self.assertEqual(len(entries), 1)
            device, lease = entries[0]
            self.assertEqual(device.serial, "m100")
            self.assertIsNotNone(lease)
            assert lease is not None
            self.assertEqual(lease.mode, "free")
            self.assertEqual(lease.destination_port, 0)
            self.assertEqual(
                server.device_servers["m100"].destination_port, 0
            )

    def test_expiry_test_lights_then_darkens_and_frees_grid(self) -> None:
        with RunningSerialOSC() as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            result = expiry_test(
                callback,
                (server.host, server.port),
                "m100",
                0.5,
                1000,
                4,
                None,
            )
            endpoint = server.device_servers["m100"]
            self.assertEqual(result.claimed.mode, "leased")
            self.assertTrue(result.claimed.owner)
            self.assertTrue(result.lost_observed)
            self.assertEqual(result.released.mode, "free")
            self.assertEqual(result.released.destination_port, 0)
            self.assertTrue(endpoint.all_dark())
            self.assertIn(("dark", "expired"), endpoint.lease_events)
            self.assertIn(("free", "expired"), endpoint.lease_events)

    def test_renew_release_test_survives_initial_ttl_then_frees_grid(self) -> None:
        with RunningSerialOSC() as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            result = renew_release_test(
                callback,
                (server.host, server.port),
                "m100",
                0.5,
                1000,
                250,
                1250,
                4,
                None,
            )
            endpoint = server.device_servers["m100"]
            self.assertEqual(result.claimed.mode, "leased")
            self.assertGreaterEqual(result.renewals, 3)
            self.assertEqual(result.maintained.mode, "leased")
            self.assertTrue(result.maintained.owner)
            self.assertEqual(result.released.mode, "free")
            self.assertEqual(result.released.destination_port, 0)
            self.assertTrue(endpoint.all_dark())
            self.assertEqual(
                endpoint.lease_events[-2:],
                [("dark", "released"), ("free", "released")],
            )

    def test_legacy_destination_requires_explicit_takeover(self) -> None:
        with RunningSerialOSC() as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            endpoint = server.device_servers["m100"]
            endpoint.set_destination("127.0.0.1", 17780, "/monome")
            with self.assertRaisesRegex(ValueError, "legacy_takeover_required"):
                expiry_test(
                    callback,
                    (server.host, server.port),
                    "m100",
                    0.5,
                    1000,
                    4,
                    None,
                )

            result = expiry_test(
                callback,
                (server.host, server.port),
                "m100",
                0.5,
                1000,
                4,
                None,
                takeover_legacy=True,
            )
            self.assertEqual(result.claimed.mode, "leased")
            self.assertEqual(result.released.mode, "free")
            self.assertTrue(endpoint.all_dark())
            self.assertIn(("leased", "takeover"), endpoint.lease_events)

    def test_zero_by_zero_padded_arc_sends_four_ring_maps(self) -> None:
        state = DeviceState(
            serial="m1001113",
            model="monome arc                       ",
            server_host="127.0.0.1",
            server_port=11564,
            destination_host="127.0.0.1",
            destination_port=0,
            prefix="/monome",
            rotation=0,
            width=0,
            height=0,
        )
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
            receiver.bind(("127.0.0.1", 0))
            receiver.settimeout(1)
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                _send_test_pattern(
                    sender,
                    receiver.getsockname(),
                    state,
                    "/test",
                    4,
                    4,
                )
            messages = [
                decode_message(receiver.recvfrom(65535)[0]) for _ in range(4)
            ]

        self.assertEqual(
            [(address, atoms[0]) for address, atoms in messages],
            [("/test/ring/map", ring) for ring in range(4)],
        )
        self.assertTrue(
            all(atoms[1:] == (4,) * 64 for _, atoms in messages)
        )

    def test_padded_arc_identity_passes_expiry_lifecycle(self) -> None:
        arc = Device(
            "m1001113",
            "monome arc                       ",
            available_udp_port(),
            rings=4,
        )
        with RunningSerialOSC((arc,)) as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            result = expiry_test(
                callback,
                (server.host, server.port),
                arc.serial,
                0.5,
                1000,
                4,
                4,
            )
            endpoint = server.device_servers[arc.serial]

        self.assertEqual(result.released.mode, "free")
        self.assertTrue(endpoint.arc_all_dark())
        self.assertTrue(endpoint.arc_messages)

    def test_invalid_arc_request_fails_before_claiming_grid(self) -> None:
        with RunningSerialOSC() as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            endpoint = server.device_servers["m100"]
            with self.assertRaisesRegex(
                ValueError, "arc_rings_supplied_for_grid"
            ):
                expiry_test(
                    callback,
                    (server.host, server.port),
                    "m100",
                    0.5,
                    1000,
                    4,
                    4,
                )

            self.assertEqual(endpoint.destination_port, 0)
            self.assertEqual(endpoint.lease_events, [])


if __name__ == "__main__":
    unittest.main()
