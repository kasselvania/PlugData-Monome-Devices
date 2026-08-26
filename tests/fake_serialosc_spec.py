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
    FakeDeviceServer,
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


class RunningDevice:
    def __init__(self, device: Device) -> None:
        self.server = FakeDeviceServer(device)
        self.stopping = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self.stopping.is_set():
            try:
                self.server.serve_once(0.01)
            except OSError:
                return

    def __enter__(self) -> FakeDeviceServer:
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
            self.assertEqual(
                receive(callback),
                ("/serialosc/add", ("m100", "monome 128", 17001)),
            )

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
                receive(callback),
                ("/serialosc/remove", ("m100", "monome 128", 17001)),
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

    def test_device_info_is_explicitly_routed_and_non_mutating(self) -> None:
        device = Device("m100", "monome 128", 0, 16, 8)
        with RunningDevice(device) as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            callback.settimeout(1)
            target = callback.getsockname()
            callback.sendto(
                encode_message("/sys/info", target[0], target[1]),
                (server.host, server.device.port),
            )

            replies = dict(receive(callback) for _ in range(6))
            self.assertEqual(replies["/sys/id"], ("m100",))
            self.assertEqual(replies["/sys/size"], (16, 8))
            self.assertEqual(replies["/sys/host"], ("127.0.0.1",))
            self.assertEqual(replies["/sys/port"], (0,))
            self.assertEqual(replies["/sys/prefix"], ("/monome",))
            self.assertEqual(server.destination_port, 0)

    def test_device_claim_settings_are_visible_in_readback(self) -> None:
        device = Device("m100", "monome 128", 0, 16, 8)
        with RunningDevice(device) as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            callback.settimeout(1)
            target = callback.getsockname()
            endpoint = (server.host, server.device.port)
            callback.sendto(encode_message("/sys/prefix", "/plugdata"), endpoint)
            callback.sendto(encode_message("/sys/host", "localhost"), endpoint)
            callback.sendto(encode_message("/sys/port", target[1]), endpoint)
            wait_until(lambda: server.destination_port == target[1])

            callback.sendto(
                encode_message("/sys/info", target[0], target[1]), endpoint
            )
            replies = dict(receive(callback) for _ in range(6))
            self.assertEqual(replies["/sys/host"], ("localhost",))
            self.assertEqual(replies["/sys/port"], (target[1],))
            self.assertEqual(replies["/sys/prefix"], ("/plugdata",))

    def test_external_displacement_replaces_destination(self) -> None:
        device = Device("m100", "monome 128", 0, 16, 8)
        with RunningDevice(device) as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            callback.settimeout(1)
            server.set_destination("127.0.0.1", 19999, "/rival")
            target = callback.getsockname()
            callback.sendto(
                encode_message("/sys/info", target[0], target[1]),
                (server.host, server.device.port),
            )
            replies = dict(receive(callback) for _ in range(6))
            self.assertEqual(replies["/sys/port"], (19999,))
            self.assertEqual(replies["/sys/prefix"], ("/rival",))

    def test_release_port_zero_keeps_explicit_info_available(self) -> None:
        device = Device("m100", "monome 128", 0, 16, 8)
        with RunningDevice(device) as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            callback.settimeout(1)
            endpoint = (server.host, server.device.port)
            callback.sendto(encode_message("/sys/port", 0), endpoint)
            wait_until(lambda: server.destination_port == 0)
            target = callback.getsockname()
            callback.sendto(
                encode_message("/sys/info", target[0], target[1]), endpoint
            )
            replies = dict(receive(callback) for _ in range(6))
            self.assertEqual(replies["/sys/port"], (0,))

    def test_grid_level_map_updates_one_8_by_8_quad_row_major(self) -> None:
        device = Device("m100", "monome 128", 0, 16, 8)
        with FakeDeviceServer(device) as server:
            levels = tuple(index % 16 for index in range(64))
            server.handle_packet(
                encode_message(
                    "/monome/grid/led/level/map", 8, 0, *levels
                )
            )

            self.assertEqual(server.level(8, 0), 0)
            self.assertEqual(server.level(15, 0), 7)
            self.assertEqual(server.level(8, 1), 8)
            self.assertEqual(server.level(15, 7), 15)
            self.assertEqual(server.level(0, 0), 0)
            self.assertEqual(len(server.grid_messages), 1)

    def test_grid_level_map_fails_closed_on_shape_offset_and_level(self) -> None:
        device = Device("m100", "monome 128", 0, 16, 8)
        with FakeDeviceServer(device) as server:
            with self.assertRaisesRegex(
                OSCError, "level_map_requires_offsets_and_64_levels"
            ):
                server.handle_packet(
                    encode_message(
                        "/monome/grid/led/level/map", 0, 0, *([0] * 63)
                    )
                )
            with self.assertRaisesRegex(OSCError, "invalid_level_map_offset"):
                server.handle_packet(
                    encode_message(
                        "/monome/grid/led/level/map", 8, 8, *([0] * 64)
                    )
                )
            with self.assertRaisesRegex(OSCError, "invalid_grid_level"):
                server.handle_packet(
                    encode_message(
                        "/monome/grid/led/level/map", 0, 0, *([16] * 64)
                    )
                )
            self.assertTrue(server.all_dark())
            self.assertEqual(server.grid_messages, [])

    def test_grid_key_uses_current_prefix_and_claimed_destination(self) -> None:
        device = Device("m100", "monome 128", 0, 16, 8)
        with FakeDeviceServer(device) as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            callback.settimeout(1)
            host, port = callback.getsockname()
            server.set_destination(host, port, "/plugdata")
            server.emit_key(15, 7, 1)
            self.assertEqual(
                receive(callback),
                ("/plugdata/grid/key", (15, 7, 1)),
            )

    def test_grid_key_requires_destination_and_valid_coordinates(self) -> None:
        device = Device("m100", "monome 128", 0, 16, 8)
        with FakeDeviceServer(device) as server:
            with self.assertRaisesRegex(ValueError, "device_has_no_destination"):
                server.emit_key(0, 0, 1)
            with self.assertRaisesRegex(ValueError, "coordinate_out_of_bounds"):
                server.emit_key(16, 0, 1)
            with self.assertRaisesRegex(ValueError, "invalid_key_state"):
                server.emit_key(0, 0, 2)

    def test_session_release_does_not_fake_grid_cleanup(self) -> None:
        device = Device("m100", "monome 128", 0, 16, 8)
        with FakeDeviceServer(device) as server:
            server.handle_packet(
                encode_message(
                    "/monome/grid/led/level/map", 0, 0, *([15] * 64)
                )
            )
            server.handle_packet(encode_message("/sys/port", 0))
            self.assertFalse(server.all_dark())

            server.handle_packet(
                encode_message(
                    "/monome/grid/led/level/map", 0, 0, *([0] * 64)
                )
            )
            server.handle_packet(
                encode_message(
                    "/monome/grid/led/level/map", 8, 0, *([0] * 64)
                )
            )
            self.assertTrue(server.all_dark())


if __name__ == "__main__":
    unittest.main(verbosity=2)
