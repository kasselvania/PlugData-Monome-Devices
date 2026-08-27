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


class ManualClock:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value

    def advance_ms(self, milliseconds: int) -> None:
        self.value += milliseconds / 1000


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

    def test_lease_info_reports_versioned_free_and_owned_state(self) -> None:
        device = Device("m100", "monome 128", 0, 16, 8)
        clock = ManualClock()
        with FakeDeviceServer(device, clock=clock) as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            callback.settimeout(1)
            host, port = callback.getsockname()

            server.handle_packet(encode_message("/sys/lease/info", host, port))
            self.assertEqual(
                receive(callback),
                (
                    "/sys/lease/state",
                    (1, "m100", "free", "127.0.0.1", 0, "/monome", 0, 0),
                ),
            )

            server.handle_packet(
                encode_message(
                    "/sys/lease/acquire",
                    "session-a",
                    host,
                    port,
                    "/plugdata",
                    6000,
                )
            )
            self.assertEqual(
                receive(callback),
                ("/sys/lease/granted", ("session-a", 6000)),
            )
            server.handle_packet(
                encode_message(
                    "/sys/lease/info", "session-a", host, port
                )
            )
            state = receive(callback)
            self.assertEqual(state[0], "/sys/lease/state")
            self.assertEqual(
                state[1],
                (
                    1,
                    "m100",
                    "leased",
                    host,
                    port,
                    "/plugdata",
                    6000,
                    1,
                ),
            )

    def test_lease_acquire_is_atomic_dark_and_nonpersistent(self) -> None:
        device = Device("m100", "monome 128", 0, 16, 8)
        clock = ManualClock()
        with FakeDeviceServer(device, clock=clock) as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            callback.settimeout(1)
            server.handle_packet(
                encode_message(
                    "/monome/grid/led/level/map", 0, 0, *([15] * 64)
                )
            )
            host, port = callback.getsockname()
            server.handle_packet(
                encode_message(
                    "/sys/lease/acquire",
                    "session-a",
                    host,
                    port,
                    "/plugdata",
                    6000,
                )
            )

            self.assertEqual(
                receive(callback),
                ("/sys/lease/granted", ("session-a", 6000)),
            )
            self.assertTrue(server.all_dark())
            self.assertEqual(
                (server.destination_host, server.destination_port, server.prefix),
                (host, port, "/plugdata"),
            )
            self.assertEqual(server.persistent_destination_port, 0)
            self.assertEqual(
                server.lease_events[:2],
                [("dark", "acquire"), ("leased", "acquire")],
            )

    def test_lease_requires_explicit_legacy_takeover(self) -> None:
        device = Device("m100", "monome 128", 0, 16, 8)
        with FakeDeviceServer(device) as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            callback.settimeout(1)
            server.set_destination("127.0.0.1", 19999, "/legacy")
            host, port = callback.getsockname()
            request = (
                "session-a",
                host,
                port,
                "/plugdata",
                6000,
            )

            server.handle_packet(encode_message("/sys/lease/acquire", *request))
            self.assertEqual(
                receive(callback),
                (
                    "/sys/lease/rejected",
                    ("session-a", "legacy_destination"),
                ),
            )
            self.assertEqual(server.destination_port, 19999)
            self.assertIsNone(server.lease_token)

            server.handle_packet(encode_message("/sys/lease/takeover", *request))
            self.assertEqual(
                receive(callback),
                ("/sys/lease/granted", ("session-a", 6000)),
            )
            self.assertEqual(server.destination_port, port)
            self.assertEqual(server.lease_token, "session-a")

    def test_lease_token_guards_retry_renew_and_release(self) -> None:
        device = Device("m100", "monome 128", 0, 16, 8)
        clock = ManualClock()
        with FakeDeviceServer(device, clock=clock) as server, bind_callback(
            "127.0.0.1", 0
        ) as owner, bind_callback("127.0.0.1", 0) as contender:
            owner.settimeout(1)
            contender.settimeout(1)
            host, port = owner.getsockname()
            request = (
                "session-a",
                host,
                port,
                "/plugdata",
                6000,
            )
            server.handle_packet(encode_message("/sys/lease/acquire", *request))
            self.assertEqual(receive(owner)[0], "/sys/lease/granted")

            clock.advance_ms(1000)
            server.handle_packet(encode_message("/sys/lease/acquire", *request))
            self.assertEqual(
                receive(owner),
                ("/sys/lease/granted", ("session-a", 6000)),
            )
            self.assertEqual(server.remaining_lease_ms(), 6000)

            server.handle_packet(
                encode_message(
                    "/sys/lease/acquire",
                    "session-a",
                    host,
                    port,
                    "/different",
                    6000,
                )
            )
            self.assertEqual(
                receive(owner),
                (
                    "/sys/lease/rejected",
                    ("session-a", "claim_mismatch"),
                ),
            )

            other_host, other_port = contender.getsockname()
            server.handle_packet(
                encode_message(
                    "/sys/lease/acquire",
                    "session-b",
                    other_host,
                    other_port,
                    "/other",
                    6000,
                )
            )
            self.assertEqual(
                receive(contender),
                ("/sys/lease/rejected", ("session-b", "busy")),
            )

            server.handle_packet(
                encode_message(
                    "/sys/lease/renew",
                    "session-b",
                    6000,
                    other_host,
                    other_port,
                )
            )
            self.assertEqual(
                receive(contender),
                ("/sys/lease/rejected", ("session-b", "not_owner")),
            )
            server.handle_packet(
                encode_message(
                    "/sys/lease/release",
                    "session-b",
                    other_host,
                    other_port,
                )
            )
            self.assertEqual(
                receive(contender),
                ("/sys/lease/rejected", ("session-b", "not_owner")),
            )
            self.assertEqual(server.lease_token, "session-a")

            clock.advance_ms(1000)
            server.handle_packet(
                encode_message(
                    "/sys/lease/renew", "session-a", 5000, host, port
                )
            )
            self.assertEqual(
                receive(owner),
                ("/sys/lease/renewed", ("session-a", 5000)),
            )
            self.assertEqual(server.remaining_lease_ms(), 5000)

    def test_lease_expiry_without_traffic_darkens_and_frees_grid(self) -> None:
        device = Device("m100", "monome 128", 0, 16, 8)
        clock = ManualClock()
        with FakeDeviceServer(device, clock=clock) as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            callback.settimeout(1)
            host, port = callback.getsockname()
            server.handle_packet(
                encode_message(
                    "/sys/lease/acquire",
                    "session-a",
                    host,
                    port,
                    "/plugdata",
                    1000,
                )
            )
            self.assertEqual(receive(callback)[0], "/sys/lease/granted")
            server.handle_packet(
                encode_message(
                    "/plugdata/grid/led/level/map", 0, 0, *([15] * 64)
                )
            )
            self.assertFalse(server.all_dark())

            clock.advance_ms(1000)
            self.assertFalse(server.serve_once(0))
            self.assertEqual(
                receive(callback),
                ("/sys/lease/lost", ("session-a", "expired")),
            )
            self.assertTrue(server.all_dark())
            self.assertEqual(server.destination_port, 0)
            self.assertIsNone(server.lease_token)
            self.assertEqual(
                server.lease_events[-2:],
                [("dark", "expired"), ("free", "expired")],
            )
            server.handle_packet(
                encode_message(
                    "/sys/lease/renew", "session-a", 1000, host, port
                )
            )
            self.assertEqual(
                receive(callback),
                ("/sys/lease/rejected", ("session-a", "no_lease")),
            )

    def test_lease_expiry_darkens_two_and_four_ring_arcs(self) -> None:
        for rings in (2, 4):
            with self.subTest(rings=rings):
                device = Device(
                    f"a{rings}00", f"monome arc {rings}", 0, rings=rings
                )
                clock = ManualClock()
                with FakeDeviceServer(
                    device, clock=clock
                ) as server, bind_callback("127.0.0.1", 0) as callback:
                    callback.settimeout(1)
                    host, port = callback.getsockname()
                    server.handle_packet(
                        encode_message(
                            "/sys/lease/acquire",
                            "session-a",
                            host,
                            port,
                            "/plugdata",
                            1000,
                        )
                    )
                    self.assertEqual(receive(callback)[0], "/sys/lease/granted")
                    for ring in range(rings):
                        server.handle_packet(
                            encode_message(
                                "/plugdata/ring/map", ring, *([15] * 64)
                            )
                        )
                    self.assertFalse(server.arc_all_dark())

                    clock.advance_ms(1000)
                    self.assertFalse(server.serve_once(0))
                    self.assertEqual(receive(callback)[0], "/sys/lease/lost")
                    self.assertTrue(server.arc_all_dark())
                    self.assertEqual(server.destination_port, 0)

    def test_matching_release_darkens_every_arc_ring(self) -> None:
        device = Device("a200", "monome arc 2", 0, rings=2)
        with FakeDeviceServer(device) as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            callback.settimeout(1)
            host, port = callback.getsockname()
            server.handle_packet(
                encode_message(
                    "/sys/lease/acquire",
                    "session-a",
                    host,
                    port,
                    "/plugdata",
                    6000,
                )
            )
            self.assertEqual(receive(callback)[0], "/sys/lease/granted")
            server.handle_packet(
                encode_message("/plugdata/ring/map", 0, *([15] * 64))
            )
            server.handle_packet(
                encode_message("/plugdata/ring/map", 1, *([8] * 64))
            )
            self.assertFalse(server.arc_all_dark())

            server.handle_packet(
                encode_message(
                    "/sys/lease/release", "session-a", host, port
                )
            )
            self.assertEqual(
                receive(callback),
                ("/sys/lease/released", ("session-a",)),
            )
            self.assertTrue(server.arc_all_dark())
            self.assertEqual(server.destination_port, 0)
            self.assertEqual(
                server.lease_events[-2:],
                [("dark", "released"), ("free", "released")],
            )

    def test_legacy_write_displaces_lease_without_darkening(self) -> None:
        device = Device("m100", "monome 128", 0, 16, 8)
        with FakeDeviceServer(device) as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            callback.settimeout(1)
            host, port = callback.getsockname()
            server.handle_packet(
                encode_message(
                    "/sys/lease/acquire",
                    "session-a",
                    host,
                    port,
                    "/plugdata",
                    6000,
                )
            )
            self.assertEqual(receive(callback)[0], "/sys/lease/granted")
            server.handle_packet(
                encode_message(
                    "/plugdata/grid/led/level/map", 0, 0, *([15] * 64)
                )
            )
            prior_dark_events = server.lease_events.count(("dark", "acquire"))

            server.handle_packet(encode_message("/sys/port", 19999))
            self.assertEqual(
                receive(callback),
                ("/sys/lease/lost", ("session-a", "legacy_write")),
            )
            self.assertIsNone(server.lease_token)
            self.assertEqual(server.destination_port, 19999)
            self.assertFalse(server.all_dark())
            self.assertEqual(
                server.lease_events.count(("dark", "acquire")),
                prior_dark_events,
            )
            self.assertEqual(server.persistent_destination_port, 19999)

    def test_invalid_lease_ttl_fails_closed(self) -> None:
        device = Device("m100", "monome 128", 0, 16, 8)
        with FakeDeviceServer(device) as server:
            with self.assertRaisesRegex(OSCError, "invalid_lease_request"):
                server.handle_packet(
                    encode_message(
                        "/sys/lease/acquire",
                        "session-a",
                        "127.0.0.1",
                        18000,
                        "/plugdata",
                        999,
                    )
                )
            self.assertEqual(server.destination_port, 0)
            self.assertIsNone(server.lease_token)

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

    def test_arc_ring_map_updates_one_ring_in_position_order(self) -> None:
        device = Device("a400", "monome arc 4", 0, rings=4)
        with FakeDeviceServer(device) as server:
            levels = tuple(index % 16 for index in range(64))
            server.handle_packet(
                encode_message("/monome/ring/map", 2, *levels)
            )

            self.assertEqual(server.ring_level(2, 0), 0)
            self.assertEqual(server.ring_level(2, 15), 15)
            self.assertEqual(server.ring_level(2, 63), 15)
            self.assertEqual(server.ring_level(0, 15), 0)
            self.assertEqual(len(server.arc_messages), 1)

    def test_arc_ring_map_fails_closed_on_shape_ring_and_level(self) -> None:
        device = Device("a400", "monome arc 4", 0, rings=4)
        with FakeDeviceServer(device) as server:
            with self.assertRaisesRegex(
                OSCError, "ring_map_requires_ring_and_64_levels"
            ):
                server.handle_packet(
                    encode_message("/monome/ring/map", 0, *([0] * 63))
                )
            with self.assertRaisesRegex(OSCError, "invalid_arc_ring"):
                server.handle_packet(
                    encode_message("/monome/ring/map", 4, *([0] * 64))
                )
            with self.assertRaisesRegex(OSCError, "invalid_arc_level"):
                server.handle_packet(
                    encode_message("/monome/ring/map", 0, *([16] * 64))
                )
            self.assertTrue(server.arc_all_dark())
            self.assertEqual(server.arc_messages, [])

    def test_arc_delta_uses_current_prefix_and_claimed_destination(self) -> None:
        device = Device("a400", "monome arc 4", 0, rings=4)
        with FakeDeviceServer(device) as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            callback.settimeout(1)
            host, port = callback.getsockname()
            server.set_destination(host, port, "/plugdata")
            server.emit_delta(3, -12)
            self.assertEqual(
                receive(callback),
                ("/plugdata/enc/delta", (3, -12)),
            )

    def test_arc_key_uses_current_prefix_when_hardware_provides_it(self) -> None:
        device = Device("a400", "monome arc 4", 0, rings=4)
        with FakeDeviceServer(device) as server, bind_callback(
            "127.0.0.1", 0
        ) as callback:
            callback.settimeout(1)
            host, port = callback.getsockname()
            server.set_destination(host, port, "/plugdata")
            server.emit_arc_key(1, 1)
            self.assertEqual(
                receive(callback),
                ("/plugdata/enc/key", (1, 1)),
            )

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
