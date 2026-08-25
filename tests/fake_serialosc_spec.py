#!/usr/bin/env python3

from __future__ import annotations

from collections.abc import Callable
import pathlib
import socket
import sys
import threading
import time
import unittest


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "tools"))

from fake_serialosc import (  # noqa: E402
    CallbackBindError,
    Device,
    FakeSerialOSC,
    OSCError,
    bind_callback,
    decode_message,
    encode_message,
)


class RunningServer:
    def __init__(self, devices: tuple[Device, ...]) -> None:
        self.server = FakeSerialOSC(port=0, devices=devices)
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


def receive(callback: socket.socket) -> tuple[str, tuple[object, ...]]:
    packet, _ = callback.recvfrom(65535)
    return decode_message(packet)


def wait_until(predicate: Callable[[], bool], timeout: float = 1) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition_not_reached")
        time.sleep(0.001)


class FakeSerialOSCTests(unittest.TestCase):
    def test_osc_codec_round_trips_discovery_types(self) -> None:
        packet = encode_message(
            "/serialosc/device", "m100", "monome 128", 17001
        )
        self.assertEqual(
            decode_message(packet),
            ("/serialosc/device", ("m100", "monome 128", 17001)),
        )
        with self.assertRaisesRegex(OSCError, "trailing_osc_data"):
            decode_message(packet + b"\0\0\0\0")

    def test_list_preserves_configured_order_and_duplicate_replies(self) -> None:
        devices = (
            Device("m200", "monome 256", 17002),
            Device("m100", "monome 128", 17001),
        )
        with RunningServer(devices) as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            callback.settimeout(1)
            server.set_reply_count("m200", 2)
            target = callback.getsockname()
            callback.sendto(
                encode_message("/serialosc/list", target[0], target[1]),
                (server.host, server.port),
            )

            replies = [receive(callback) for _ in range(3)]
            self.assertEqual(
                replies,
                [
                    ("/serialosc/device", ("m200", "monome 256", 17002)),
                    ("/serialosc/device", ("m200", "monome 256", 17002)),
                    ("/serialosc/device", ("m100", "monome 128", 17001)),
                ],
            )

    def test_notify_is_one_shot_and_rearms_explicitly(self) -> None:
        with RunningServer(()) as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            callback.settimeout(0.15)
            target = callback.getsockname()

            callback.sendto(
                encode_message("/serialosc/notify", target[0], target[1]),
                (server.host, server.port),
            )
            wait_until(lambda: server.notify_target == target)
            server.add(Device("m100", "monome 128", 17001))
            self.assertEqual(receive(callback), ("/serialosc/add", ("m100",)))

            server.add(Device("m200", "monome 256", 17002))
            with self.assertRaises(socket.timeout):
                receive(callback)

            callback.sendto(
                encode_message("/serialosc/notify", target[0], target[1]),
                (server.host, server.port),
            )
            wait_until(lambda: server.notify_target == target)
            server.remove("m100")
            self.assertEqual(
                receive(callback), ("/serialosc/remove", ("m100",))
            )

    def test_reorder_changes_replies_without_changing_identity(self) -> None:
        devices = (
            Device("m100", "monome 128", 17001),
            Device("m200", "monome 256", 17002),
        )
        with RunningServer(devices) as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            callback.settimeout(1)
            server.reorder(["m200", "m100"])
            target = callback.getsockname()
            callback.sendto(
                encode_message("/serialosc/list", target[0], target[1]),
                (server.host, server.port),
            )
            serials = [receive(callback)[1][0] for _ in range(2)]
            self.assertEqual(serials, ["m200", "m100"])

    def test_callback_collision_fails_with_explicit_error(self) -> None:
        with bind_callback("127.0.0.1", 0) as first:
            host, port = first.getsockname()
            with self.assertRaisesRegex(
                CallbackBindError, f"callback_unavailable {host} {port}"
            ):
                bind_callback(host, port)

    def test_fake_server_refuses_the_live_serialosc_port(self) -> None:
        with self.assertRaisesRegex(ValueError, "refusing_live_serialosc_port"):
            FakeSerialOSC(port=12002)


if __name__ == "__main__":
    unittest.main(verbosity=2)
