#!/usr/bin/env python3

from __future__ import annotations

import pathlib
import socket
import sys
import threading
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from fake_serialosc import Device, FakeSerialOSC, bind_callback  # noqa: E402
from live_serialosc_lease import expiry_test, lease_snapshot  # noqa: E402


def available_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as candidate:
        candidate.bind(("127.0.0.1", 0))
        return candidate.getsockname()[1]


class RunningSerialOSC:
    def __init__(self) -> None:
        self.server = FakeSerialOSC(
            port=0,
            devices=(
                Device(
                    "m100",
                    "monome 128",
                    available_udp_port(),
                    16,
                    8,
                ),
            ),
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


if __name__ == "__main__":
    unittest.main()
