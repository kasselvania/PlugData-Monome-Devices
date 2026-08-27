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
from live_serialosc_state import snapshot  # noqa: E402


def available_udp_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as candidate:
        candidate.bind(("127.0.0.1", 0))
        return candidate.getsockname()[1]


class RunningSerialOSC:
    def __init__(self) -> None:
        grid_port = available_udp_port()
        arc_port = available_udp_port()
        while arc_port == grid_port:
            arc_port = available_udp_port()
        self.server = FakeSerialOSC(
            port=0,
            devices=(
                Device("m100", "monome 128", grid_port, 16, 8),
                Device("a400", "monome arc 4", arc_port, rings=4),
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


class LiveSerialOSCStateTests(unittest.TestCase):
    def test_snapshot_reads_every_destination_without_mutating_it(self) -> None:
        with RunningSerialOSC() as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            server.device_servers["m100"].set_destination(
                "127.0.0.1", 19996, "/rival"
            )

            states = snapshot(callback, (server.host, server.port), 0.5)

            self.assertEqual([state.serial for state in states], ["m100", "a400"])
            self.assertEqual(states[0].destination_port, 19996)
            self.assertEqual(states[0].prefix, "/rival")
            self.assertEqual((states[0].width, states[0].height), (16, 8))
            self.assertEqual(states[1].destination_port, 0)
            self.assertEqual((states[1].width, states[1].height), (None, None))
            self.assertEqual(
                server.device_servers["m100"].destination_port, 19996
            )
            self.assertEqual(server.device_servers["a400"].destination_port, 0)


if __name__ == "__main__":
    unittest.main()
