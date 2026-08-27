#!/usr/bin/env python3
"""Small, dependency-free SerialOSC workbench for development.

The simulator speaks the discovery and per-device system messages used by this
project. It never opens a serial device and refuses SerialOSC's live port 12002.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, replace
import math
import select
import shlex
import socket
import struct
import sys
import time
from typing import Iterable


LIVE_SERIALOSC_PORT = 12002
DEFAULT_FAKE_PORT = 12012
DEFAULT_ARC_PORT = 17003
LEASE_PROTOCOL_VERSION = 1
MIN_LEASE_TTL_MS = 1000
MAX_LEASE_TTL_MS = 60000
MAX_LEASE_TOKEN_BYTES = 128


class OSCError(ValueError):
    """Raised for malformed or unsupported OSC packets."""


class CallbackBindError(OSError):
    """Raised when a discovery callback port is unavailable."""


@dataclass(frozen=True)
class Device:
    serial: str
    model: str
    port: int
    width: int | None = None
    height: int | None = None
    rings: int | None = None


DEFAULT_DEVICES = (
    Device("m100", "monome 128", 17001, 16, 8),
    Device("m200", "monome 256", 17002, 16, 16),
)


def default_arc(rings: int) -> Device:
    if rings not in (2, 4):
        raise ValueError("unsupported_ring_count")
    return Device(
        f"a{rings}00",
        f"monome arc {rings}",
        DEFAULT_ARC_PORT,
        rings=rings,
    )


def _encode_string(value: str) -> bytes:
    if not isinstance(value, str) or not value or "\0" in value:
        raise OSCError("invalid_osc_string")
    encoded = value.encode("utf-8") + b"\0"
    return encoded + (b"\0" * ((-len(encoded)) % 4))


def encode_message(address: str, *arguments: object) -> bytes:
    if not address.startswith("/"):
        raise OSCError("invalid_osc_address")

    tags = []
    payload = []
    for argument in arguments:
        if isinstance(argument, bool):
            raise OSCError("unsupported_osc_argument")
        if isinstance(argument, int):
            if argument < -(2**31) or argument >= 2**31:
                raise OSCError("osc_integer_out_of_range")
            tags.append("i")
            payload.append(struct.pack(">i", argument))
        elif isinstance(argument, str):
            tags.append("s")
            payload.append(_encode_string(argument))
        else:
            raise OSCError("unsupported_osc_argument")

    return b"".join(
        (_encode_string(address), _encode_string("," + "".join(tags)), *payload)
    )


def _decode_string(packet: bytes, offset: int) -> tuple[str, int]:
    end = packet.find(b"\0", offset)
    if end < 0:
        raise OSCError("unterminated_osc_string")
    next_offset = (end + 4) & ~3
    if next_offset > len(packet):
        raise OSCError("truncated_osc_string")
    if any(packet[end:next_offset]):
        raise OSCError("nonzero_osc_padding")
    try:
        value = packet[offset:end].decode("utf-8")
    except UnicodeDecodeError as error:
        raise OSCError("invalid_osc_utf8") from error
    return value, next_offset


def decode_message(packet: bytes) -> tuple[str, tuple[object, ...]]:
    if not isinstance(packet, bytes) or not packet:
        raise OSCError("empty_osc_packet")

    address, offset = _decode_string(packet, 0)
    if not address.startswith("/"):
        raise OSCError("invalid_osc_address")
    tags, offset = _decode_string(packet, offset)
    if not tags.startswith(","):
        raise OSCError("missing_osc_type_tag")

    arguments: list[object] = []
    for tag in tags[1:]:
        if tag == "s":
            value, offset = _decode_string(packet, offset)
            arguments.append(value)
        elif tag == "i":
            if offset + 4 > len(packet):
                raise OSCError("truncated_osc_integer")
            arguments.append(struct.unpack(">i", packet[offset : offset + 4])[0])
            offset += 4
        else:
            raise OSCError("unsupported_osc_type")

    if offset != len(packet):
        raise OSCError("trailing_osc_data")
    return address, tuple(arguments)


def bind_callback(host: str, port: int) -> socket.socket:
    callback = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        callback.bind((host, port))
    except OSError as error:
        callback.close()
        raise CallbackBindError(f"callback_unavailable {host} {port}") from error
    return callback


class FakeDeviceServer:
    """A fake per-device SerialOSC server with mutable application settings."""

    def __init__(
        self,
        device: Device,
        host: str = "127.0.0.1",
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if device.port < 0 or device.port > 65535:
            raise ValueError("invalid_device_port")
        if (device.width is None) != (device.height is None):
            raise ValueError("incomplete_device_size")
        if device.width is not None and (
            device.width < 1 or device.height is None or device.height < 1
        ):
            raise ValueError("invalid_device_size")
        if device.rings is not None and device.rings not in (2, 4):
            raise ValueError("unsupported_ring_count")
        if device.rings is not None and device.width is not None:
            raise ValueError("ambiguous_device_surface")

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((host, device.port))
        self.host, actual_port = self.socket.getsockname()
        self.device = replace(device, port=actual_port)
        self.destination_host = "127.0.0.1"
        self.destination_port = 0
        self.prefix = "/monome"
        self.persistent_destination_host = self.destination_host
        self.persistent_destination_port = self.destination_port
        self.persistent_prefix = self.prefix
        self.lease_token: str | None = None
        self.lease_deadline: float | None = None
        self.lease_ttl_ms = 0
        self.lease_events: list[tuple[str, str]] = []
        self._clock = clock
        self.rotation = 0
        surface = (device.width or 0) * (device.height or 0)
        self.levels = [0] * surface
        self.grid_messages: list[tuple[str, tuple[object, ...]]] = []
        self.ring_levels = [
            [0] * 64 for _ in range(device.rings or 0)
        ]
        self.arc_messages: list[tuple[str, tuple[object, ...]]] = []

    def close(self) -> None:
        self.socket.close()

    def __enter__(self) -> FakeDeviceServer:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @staticmethod
    def _port(arguments: tuple[object, ...], allow_zero: bool) -> int:
        minimum = 0 if allow_zero else 1
        if (
            len(arguments) != 1
            or not isinstance(arguments[0], int)
            or arguments[0] < minimum
            or arguments[0] > 65535
        ):
            raise OSCError("invalid_sys_port")
        return arguments[0]

    @staticmethod
    def _string(arguments: tuple[object, ...], error: str) -> str:
        if len(arguments) != 1 or not isinstance(arguments[0], str):
            raise OSCError(error)
        return arguments[0]

    @staticmethod
    def _info_target(
        arguments: tuple[object, ...],
        default_host: str,
        default_port: int,
    ) -> tuple[str, int] | None:
        if len(arguments) == 0:
            if default_port == 0:
                return None
            return socket.gethostbyname(default_host), default_port
        if len(arguments) == 1:
            port = FakeDeviceServer._port(arguments, allow_zero=False)
            return "127.0.0.1", port
        if (
            len(arguments) == 2
            and isinstance(arguments[0], str)
            and isinstance(arguments[1], int)
            and 1 <= arguments[1] <= 65535
        ):
            return socket.gethostbyname(arguments[0]), arguments[1]
        raise OSCError("invalid_sys_info_target")

    def _send_info(self, target: tuple[str, int]) -> None:
        messages: list[tuple[str, tuple[object, ...]]] = [
            ("/sys/id", (self.device.serial,)),
        ]
        if self.device.width is not None and self.device.height is not None:
            messages.append(
                ("/sys/size", (self.device.width, self.device.height))
            )
        messages.extend(
            (
                ("/sys/host", (self.destination_host,)),
                ("/sys/port", (self.destination_port,)),
                ("/sys/prefix", (self.prefix,)),
                ("/sys/rotation", (self.rotation,)),
            )
        )
        for address, arguments in messages:
            self.socket.sendto(encode_message(address, *arguments), target)

    @staticmethod
    def _reply_target(host: object, port: object) -> tuple[str, int]:
        if (
            not isinstance(host, str)
            or not host
            or not isinstance(port, int)
            or port < 1
            or port > 65535
        ):
            raise OSCError("invalid_lease_request")
        try:
            return socket.gethostbyname(host), port
        except OSError as error:
            raise OSCError("invalid_lease_request") from error

    @staticmethod
    def _lease_identity(token: object) -> str:
        if (
            not isinstance(token, str)
            or not token
            or len(token.encode("utf-8")) > MAX_LEASE_TOKEN_BYTES
        ):
            raise OSCError("invalid_lease_request")
        return token

    @staticmethod
    def _lease_ttl(ttl_ms: object) -> int:
        if (
            not isinstance(ttl_ms, int)
            or ttl_ms < MIN_LEASE_TTL_MS
            or ttl_ms > MAX_LEASE_TTL_MS
        ):
            raise OSCError("invalid_lease_request")
        return ttl_ms

    @staticmethod
    def _lease_prefix(prefix: object) -> str:
        if not isinstance(prefix, str) or not prefix.startswith("/"):
            raise OSCError("invalid_lease_request")
        return prefix

    def _send(self, target: tuple[str, int], address: str, *arguments: object) -> None:
        self.socket.sendto(encode_message(address, *arguments), target)

    def lease_mode(self) -> str:
        if self.lease_token is not None:
            return "leased"
        if self.destination_port == 0:
            return "free"
        return "legacy"

    def remaining_lease_ms(self) -> int:
        if self.lease_deadline is None:
            return 0
        return max(0, math.ceil((self.lease_deadline - self._clock()) * 1000))

    def next_lease_timeout(self) -> float | None:
        if self.lease_deadline is None:
            return None
        return max(0.0, self.lease_deadline - self._clock())

    def _dark_surface(self, reason: str) -> None:
        self.levels = [0] * len(self.levels)
        self.ring_levels = [[0] * 64 for _ in self.ring_levels]
        self.lease_events.append(("dark", reason))

    def _set_free_after_lease(self, reason: str) -> None:
        self.destination_host = self.persistent_destination_host
        self.destination_port = 0
        self.prefix = self.persistent_prefix
        self.persistent_destination_port = 0
        self.lease_token = None
        self.lease_deadline = None
        self.lease_ttl_ms = 0
        self.lease_events.append(("free", reason))

    def expire_lease_if_due(self) -> bool:
        if self.lease_deadline is None or self._clock() < self.lease_deadline:
            return False
        token = self.lease_token
        target = self._reply_target(self.destination_host, self.destination_port)
        self._dark_surface("expired")
        if token is not None:
            self._send(target, "/sys/lease/lost", token, "expired")
        self._set_free_after_lease("expired")
        return True

    def _cancel_lease_for_legacy_write(self) -> None:
        if self.lease_token is None:
            return
        token = self.lease_token
        target = self._reply_target(self.destination_host, self.destination_port)
        self._send(target, "/sys/lease/lost", token, "legacy_write")
        self.persistent_destination_host = self.destination_host
        self.persistent_destination_port = self.destination_port
        self.persistent_prefix = self.prefix
        self.lease_token = None
        self.lease_deadline = None
        self.lease_ttl_ms = 0
        self.lease_events.append(("legacy", "legacy_write"))

    def _lease_destination(
        self, arguments: tuple[object, ...]
    ) -> tuple[str, str, int, str, int, tuple[str, int]]:
        if len(arguments) != 5:
            raise OSCError("invalid_lease_request")
        token = self._lease_identity(arguments[0])
        host = arguments[1]
        port = arguments[2]
        prefix = self._lease_prefix(arguments[3])
        ttl_ms = self._lease_ttl(arguments[4])
        target = self._reply_target(host, port)
        assert isinstance(host, str)
        assert isinstance(port, int)
        return token, host, port, prefix, ttl_ms, target

    def _handle_lease_info(self, arguments: tuple[object, ...]) -> None:
        token: str | None = None
        if len(arguments) == 2:
            host, port = arguments
        elif len(arguments) == 3:
            token = self._lease_identity(arguments[0])
            host, port = arguments[1:]
        else:
            raise OSCError("invalid_lease_request")
        target = self._reply_target(host, port)
        owner = int(token is not None and token == self.lease_token)
        self._send(
            target,
            "/sys/lease/state",
            LEASE_PROTOCOL_VERSION,
            self.device.serial,
            self.lease_mode(),
            self.destination_host,
            self.destination_port,
            self.prefix,
            self.remaining_lease_ms(),
            owner,
        )

    def _handle_lease_acquire(
        self, arguments: tuple[object, ...], takeover: bool
    ) -> None:
        token, host, port, prefix, ttl_ms, target = self._lease_destination(
            arguments
        )
        if self.lease_token is not None:
            if token != self.lease_token:
                self._send(target, "/sys/lease/rejected", token, "busy")
                return
            if (
                host != self.destination_host
                or port != self.destination_port
                or prefix != self.prefix
            ):
                self._send(
                    target,
                    "/sys/lease/rejected",
                    token,
                    "claim_mismatch",
                )
                return
            self.lease_ttl_ms = ttl_ms
            self.lease_deadline = self._clock() + (ttl_ms / 1000)
            self._send(target, "/sys/lease/granted", token, ttl_ms)
            return

        if self.destination_port != 0 and not takeover:
            self._send(
                target,
                "/sys/lease/rejected",
                token,
                "legacy_destination",
            )
            return

        reason = "takeover" if takeover and self.destination_port != 0 else "acquire"
        self._dark_surface(reason)
        self.persistent_destination_port = 0
        self.destination_host = host
        self.destination_port = port
        self.prefix = prefix
        self.lease_token = token
        self.lease_ttl_ms = ttl_ms
        self.lease_deadline = self._clock() + (ttl_ms / 1000)
        self.lease_events.append(("leased", reason))
        self._send(target, "/sys/lease/granted", token, ttl_ms)

    def _lease_reply_request(
        self,
        arguments: tuple[object, ...],
        include_ttl: bool,
    ) -> tuple[str, int | None, tuple[str, int]]:
        expected = 4 if include_ttl else 3
        if len(arguments) != expected:
            raise OSCError("invalid_lease_request")
        token = self._lease_identity(arguments[0])
        if include_ttl:
            ttl_ms: int | None = self._lease_ttl(arguments[1])
            host, port = arguments[2:]
        else:
            ttl_ms = None
            host, port = arguments[1:]
        return token, ttl_ms, self._reply_target(host, port)

    def _handle_lease_renew(self, arguments: tuple[object, ...]) -> None:
        token, ttl_ms, target = self._lease_reply_request(arguments, True)
        assert ttl_ms is not None
        if self.lease_token is None:
            self._send(target, "/sys/lease/rejected", token, "no_lease")
            return
        if token != self.lease_token:
            self._send(target, "/sys/lease/rejected", token, "not_owner")
            return
        self.lease_ttl_ms = ttl_ms
        self.lease_deadline = self._clock() + (ttl_ms / 1000)
        self._send(target, "/sys/lease/renewed", token, ttl_ms)

    def _handle_lease_release(self, arguments: tuple[object, ...]) -> None:
        token, _, target = self._lease_reply_request(arguments, False)
        if self.lease_token is None:
            self._send(target, "/sys/lease/rejected", token, "no_lease")
            return
        if token != self.lease_token:
            self._send(target, "/sys/lease/rejected", token, "not_owner")
            return
        self._dark_surface("released")
        self._set_free_after_lease("released")
        self._send(target, "/sys/lease/released", token)

    def _grid_size(self) -> tuple[int, int]:
        if self.device.width is None or self.device.height is None:
            raise OSCError("device_has_no_grid")
        return self.device.width, self.device.height

    def _handle_level_map(
        self, address: str, arguments: tuple[object, ...]
    ) -> None:
        width, height = self._grid_size()
        if len(arguments) != 66:
            raise OSCError("level_map_requires_offsets_and_64_levels")
        x_offset, y_offset = arguments[:2]
        if (
            not isinstance(x_offset, int)
            or not isinstance(y_offset, int)
            or x_offset < 0
            or y_offset < 0
            or x_offset % 8 != 0
            or y_offset % 8 != 0
            or x_offset + 8 > width
            or y_offset + 8 > height
        ):
            raise OSCError("invalid_level_map_offset")
        levels = arguments[2:]
        if any(
            not isinstance(level, int) or level < 0 or level > 15
            for level in levels
        ):
            raise OSCError("invalid_grid_level")

        source = 0
        for y in range(y_offset, y_offset + 8):
            for x in range(x_offset, x_offset + 8):
                self.levels[(y * width) + x] = levels[source]
                source += 1
        self.grid_messages.append((address, arguments))

    def _arc_ring_count(self) -> int:
        if self.device.rings is None:
            raise OSCError("device_has_no_arc")
        return self.device.rings

    def _handle_ring_map(
        self, address: str, arguments: tuple[object, ...]
    ) -> None:
        rings = self._arc_ring_count()
        if len(arguments) != 65:
            raise OSCError("ring_map_requires_ring_and_64_levels")
        ring = arguments[0]
        if not isinstance(ring, int) or ring < 0 or ring >= rings:
            raise OSCError("invalid_arc_ring")
        levels = arguments[1:]
        if any(
            not isinstance(level, int) or level < 0 or level > 15
            for level in levels
        ):
            raise OSCError("invalid_arc_level")
        self.ring_levels[ring] = list(levels)
        self.arc_messages.append((address, arguments))

    def handle_packet(self, packet: bytes) -> None:
        self.expire_lease_if_due()
        address, arguments = decode_message(packet)
        if address == "/sys/info":
            target = self._info_target(
                arguments, self.destination_host, self.destination_port
            )
            if target is not None:
                self._send_info(target)
        elif address == "/sys/lease/info":
            self._handle_lease_info(arguments)
        elif address == "/sys/lease/acquire":
            self._handle_lease_acquire(arguments, takeover=False)
        elif address == "/sys/lease/takeover":
            self._handle_lease_acquire(arguments, takeover=True)
        elif address == "/sys/lease/renew":
            self._handle_lease_renew(arguments)
        elif address == "/sys/lease/release":
            self._handle_lease_release(arguments)
        elif address == "/sys/host":
            host = self._string(arguments, "invalid_sys_host")
            self._cancel_lease_for_legacy_write()
            self.destination_host = host
            self.persistent_destination_host = host
        elif address == "/sys/port":
            port = self._port(arguments, allow_zero=True)
            self._cancel_lease_for_legacy_write()
            self.destination_port = port
            self.persistent_destination_port = port
        elif address == "/sys/prefix":
            prefix = self._string(arguments, "invalid_sys_prefix")
            if not prefix.startswith("/"):
                raise OSCError("invalid_sys_prefix")
            self._cancel_lease_for_legacy_write()
            self.prefix = prefix
            self.persistent_prefix = prefix
        elif address == "/sys/rotation":
            rotation = self._port(arguments, allow_zero=True)
            if rotation not in (0, 90, 180, 270):
                raise OSCError("invalid_sys_rotation")
            self.rotation = rotation
        elif address == self.prefix + "/grid/led/level/map":
            self._handle_level_map(address, arguments)
        elif address == self.prefix + "/ring/map":
            self._handle_ring_map(address, arguments)
        else:
            raise OSCError("unsupported_device_message")

    def serve_once(self, timeout: float = 0.1) -> bool:
        self.expire_lease_if_due()
        lease_timeout = self.next_lease_timeout()
        if lease_timeout is not None:
            timeout = min(timeout, lease_timeout)
        readable, _, _ = select.select([self.socket], [], [], timeout)
        if not readable:
            self.expire_lease_if_due()
            return False
        packet, _ = self.socket.recvfrom(65535)
        self.handle_packet(packet)
        return True

    def set_destination(self, host: str, port: int, prefix: str) -> None:
        if not host or port < 0 or port > 65535 or not prefix.startswith("/"):
            raise ValueError("invalid_destination")
        self._cancel_lease_for_legacy_write()
        self.destination_host = host
        self.destination_port = port
        self.prefix = prefix
        self.persistent_destination_host = host
        self.persistent_destination_port = port
        self.persistent_prefix = prefix

    def level(self, x: int, y: int) -> int:
        width, height = self._grid_size()
        if x < 0 or y < 0 or x >= width or y >= height:
            raise ValueError("coordinate_out_of_bounds")
        return self.levels[(y * width) + x]

    def all_dark(self) -> bool:
        self._grid_size()
        return all(level == 0 for level in self.levels)

    def ring_level(self, ring: int, position: int) -> int:
        rings = self._arc_ring_count()
        if ring < 0 or ring >= rings or position < 0 or position >= 64:
            raise ValueError("arc_coordinate_out_of_bounds")
        return self.ring_levels[ring][position]

    def arc_all_dark(self) -> bool:
        self._arc_ring_count()
        return all(
            level == 0
            for ring in self.ring_levels
            for level in ring
        )

    def emit_key(self, x: int, y: int, state: int) -> None:
        width, height = self._grid_size()
        if x < 0 or y < 0 or x >= width or y >= height:
            raise ValueError("coordinate_out_of_bounds")
        if state not in (0, 1):
            raise ValueError("invalid_key_state")
        if self.destination_port == 0:
            raise ValueError("device_has_no_destination")
        target = (
            socket.gethostbyname(self.destination_host),
            self.destination_port,
        )
        self.socket.sendto(
            encode_message(self.prefix + "/grid/key", x, y, state), target
        )

    def emit_delta(self, ring: int, delta: int) -> None:
        rings = self._arc_ring_count()
        if type(ring) is not int or ring < 0 or ring >= rings:
            raise ValueError("arc_ring_out_of_bounds")
        if type(delta) is not int:
            raise ValueError("invalid_arc_delta")
        if self.destination_port == 0:
            raise ValueError("device_has_no_destination")
        target = (
            socket.gethostbyname(self.destination_host),
            self.destination_port,
        )
        self.socket.sendto(
            encode_message(self.prefix + "/enc/delta", ring, delta), target
        )

    def emit_arc_key(self, ring: int, state: int) -> None:
        rings = self._arc_ring_count()
        if type(ring) is not int or ring < 0 or ring >= rings:
            raise ValueError("arc_ring_out_of_bounds")
        if state not in (0, 1):
            raise ValueError("invalid_key_state")
        if self.destination_port == 0:
            raise ValueError("device_has_no_destination")
        target = (
            socket.gethostbyname(self.destination_host),
            self.destination_port,
        )
        self.socket.sendto(
            encode_message(self.prefix + "/enc/key", ring, state), target
        )


class FakeSerialOSC:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = DEFAULT_FAKE_PORT,
        devices: Iterable[Device] = DEFAULT_DEVICES,
        spawn_device_servers: bool = False,
    ) -> None:
        if port == LIVE_SERIALOSC_PORT:
            raise ValueError("refusing_live_serialosc_port")

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((host, port))
        self.host, self.port = self.socket.getsockname()
        self.devices: dict[str, Device] = {}
        self.order: list[str] = []
        self.reply_counts: dict[str, int] = {}
        self.notify_target: tuple[str, int] | None = None
        self.spawn_device_servers = spawn_device_servers
        self.device_servers: dict[str, FakeDeviceServer] = {}
        self.initial_devices = tuple(devices)

        try:
            for device in self.initial_devices:
                self._add_device(device)
        except (ValueError, OSError):
            self.close()
            raise

    @staticmethod
    def _validate_device(device: Device) -> None:
        if not device.serial or not device.model:
            raise ValueError("invalid_device")
        if device.port < 1 or device.port > 65535:
            raise ValueError("invalid_device_port")
        if (device.width is None) != (device.height is None):
            raise ValueError("incomplete_device_size")
        if device.width is not None and (
            device.width < 1 or device.height is None or device.height < 1
        ):
            raise ValueError("invalid_device_size")
        if device.rings is not None and device.rings not in (2, 4):
            raise ValueError("unsupported_ring_count")
        if device.rings is not None and device.width is not None:
            raise ValueError("ambiguous_device_surface")

    def _add_device(self, device: Device) -> Device:
        self._validate_device(device)
        if device.serial in self.devices:
            raise ValueError("duplicate_device_serial")
        resolved = device
        if self.spawn_device_servers:
            endpoint = FakeDeviceServer(device, self.host)
            resolved = endpoint.device
            self.device_servers[resolved.serial] = endpoint
        self.devices[resolved.serial] = resolved
        self.order.append(resolved.serial)
        return resolved

    @staticmethod
    def _target(arguments: tuple[object, ...]) -> tuple[str, int]:
        if (
            len(arguments) != 2
            or not isinstance(arguments[0], str)
            or not isinstance(arguments[1], int)
            or arguments[1] < 1
            or arguments[1] > 65535
        ):
            raise OSCError("discovery_target_requires_host_port")
        return socket.gethostbyname(arguments[0]), arguments[1]

    def close(self) -> None:
        for endpoint in self.device_servers.values():
            endpoint.close()
        self.device_servers = {}
        self.socket.close()

    def __enter__(self) -> FakeSerialOSC:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _send(self, target: tuple[str, int], address: str, *arguments: object) -> None:
        self.socket.sendto(encode_message(address, *arguments), target)

    def handle_packet(self, packet: bytes) -> None:
        address, arguments = decode_message(packet)
        if address == "/serialosc/list":
            target = self._target(arguments)
            for serial in self.order:
                device = self.devices[serial]
                for _ in range(self.reply_counts.get(serial, 1)):
                    self._send(
                        target,
                        "/serialosc/device",
                        device.serial,
                        device.model,
                        device.port,
                    )
        elif address == "/serialosc/notify":
            self.notify_target = self._target(arguments)
        else:
            raise OSCError("unsupported_discovery_message")

    def serve_once(self, timeout: float = 0.1) -> bool:
        for endpoint in self.device_servers.values():
            endpoint.expire_lease_if_due()
        lease_timeouts = [
            endpoint.next_lease_timeout()
            for endpoint in self.device_servers.values()
        ]
        active_timeouts = [value for value in lease_timeouts if value is not None]
        if active_timeouts:
            timeout = min(timeout, min(active_timeouts))
        readable, _, _ = select.select(self.sockets, [], [], timeout)
        if not readable:
            for endpoint in self.device_servers.values():
                endpoint.expire_lease_if_due()
            return False
        self.serve_socket(readable[0])
        return True

    @property
    def sockets(self) -> list[socket.socket]:
        return [self.socket] + [
            endpoint.socket for endpoint in self.device_servers.values()
        ]

    def serve_socket(self, readable: socket.socket) -> None:
        packet, _ = readable.recvfrom(65535)
        if readable is self.socket:
            self.handle_packet(packet)
            return
        for endpoint in self.device_servers.values():
            if readable is endpoint.socket:
                endpoint.handle_packet(packet)
                return
        raise OSError("unknown_server_socket")

    def _notify_once(self, address: str, device: Device) -> None:
        if self.notify_target is None:
            return
        target = self.notify_target
        self.notify_target = None
        self._send(
            target,
            address,
            device.serial,
            device.model,
            device.port,
        )

    def add(self, device: Device) -> None:
        resolved = self._add_device(device)
        self._notify_once("/serialosc/add", resolved)

    def remove(self, serial: str) -> None:
        if serial not in self.devices:
            raise ValueError("unknown_device")
        device = self.devices[serial]
        del self.devices[serial]
        self.order.remove(serial)
        self.reply_counts.pop(serial, None)
        endpoint = self.device_servers.pop(serial, None)
        if endpoint:
            endpoint.close()
        self._notify_once("/serialosc/remove", device)

    def reorder(self, serials: list[str]) -> None:
        if len(serials) != len(set(serials)) or set(serials) != set(self.devices):
            raise ValueError("order_must_name_each_device_once")
        self.order = list(serials)

    def set_reply_count(self, serial: str, count: int) -> None:
        if serial not in self.devices:
            raise ValueError("unknown_device")
        if count < 1:
            raise ValueError("reply_count_must_be_positive")
        self.reply_counts[serial] = count

    def reset(self) -> None:
        for endpoint in self.device_servers.values():
            endpoint.close()
        self.device_servers = {}
        self.devices = {}
        self.order = []
        self.reply_counts = {}
        for device in self.initial_devices:
            self._add_device(device)

    def displace(self, serial: str, host: str, port: int, prefix: str) -> None:
        endpoint = self.device_servers.get(serial)
        if endpoint is None:
            raise ValueError("device_servers_disabled")
        endpoint.set_destination(host, port, prefix)

    def device_state(self, serial: str) -> tuple[str, int, str]:
        endpoint = self.device_servers.get(serial)
        if endpoint is None:
            raise ValueError("device_servers_disabled")
        return (
            endpoint.destination_host,
            endpoint.destination_port,
            endpoint.prefix,
        )

    def emit_key(self, serial: str, x: int, y: int, state: int) -> None:
        endpoint = self.device_servers.get(serial)
        if endpoint is None:
            raise ValueError("device_servers_disabled")
        endpoint.emit_key(x, y, state)

    def emit_delta(self, serial: str, ring: int, delta: int) -> None:
        endpoint = self.device_servers.get(serial)
        if endpoint is None:
            raise ValueError("device_servers_disabled")
        endpoint.emit_delta(ring, delta)

    def emit_arc_key(self, serial: str, ring: int, state: int) -> None:
        endpoint = self.device_servers.get(serial)
        if endpoint is None:
            raise ValueError("device_servers_disabled")
        endpoint.emit_arc_key(ring, state)

    def grid_rows(self, serial: str) -> list[list[int]]:
        endpoint = self.device_servers.get(serial)
        if endpoint is None:
            raise ValueError("device_servers_disabled")
        width, height = endpoint._grid_size()
        return [
            [endpoint.level(x, y) for x in range(width)] for y in range(height)
        ]

    def arc_rings(self, serial: str) -> list[list[int]]:
        endpoint = self.device_servers.get(serial)
        if endpoint is None:
            raise ValueError("device_servers_disabled")
        endpoint._arc_ring_count()
        return [list(levels) for levels in endpoint.ring_levels]


def _print_devices(server: FakeSerialOSC) -> None:
    for serial in server.order:
        device = server.devices[serial]
        print(f'DEVICE {device.serial} "{device.model}" {device.port}', flush=True)


def _print_state(server: FakeSerialOSC, serials: Iterable[str]) -> None:
    for serial in serials:
        host, port, prefix = server.device_state(serial)
        print(f'STATE {serial} "{host}" {port} "{prefix}"', flush=True)


def _print_grid(server: FakeSerialOSC, serial: str) -> None:
    print(f"GRID {serial}", flush=True)
    for row in server.grid_rows(serial):
        print("".join(format(level, "x") for level in row), flush=True)


def _print_arc(server: FakeSerialOSC, serial: str) -> None:
    print(f"ARC {serial}", flush=True)
    for ring, levels in enumerate(server.arc_rings(serial)):
        print(f"{ring} " + "".join(format(level, "x") for level in levels), flush=True)


def _device_with_inferred_size(serial: str, model: str, port: int) -> Device:
    if "256" in model:
        return Device(serial, model, port, 16, 16)
    if "128" in model:
        return Device(serial, model, port, 16, 8)
    return Device(serial, model, port)


def _command(server: FakeSerialOSC, line: str) -> bool:
    words = shlex.split(line)
    if not words:
        return True
    command, arguments = words[0], words[1:]

    if command == "help":
        print(
            'COMMANDS: devices | add SERIAL "MODEL" PORT | remove SERIAL | '
            "order SERIAL... | duplicate SERIAL COUNT | "
            "state [SERIAL] | displace SERIAL HOST PORT PREFIX | "
            "key SERIAL X Y STATE | grid SERIAL | "
            "delta SERIAL RING AMOUNT | arc_key SERIAL RING STATE | "
            "arc SERIAL | reset | quit",
            flush=True,
        )
    elif command == "devices" and not arguments:
        _print_devices(server)
    elif command == "add" and len(arguments) == 3:
        server.add(
            _device_with_inferred_size(
                arguments[0], arguments[1], int(arguments[2])
            )
        )
        print(f"OK added {arguments[0]}", flush=True)
    elif command == "remove" and len(arguments) == 1:
        server.remove(arguments[0])
        print(f"OK removed {arguments[0]}", flush=True)
    elif command == "order" and arguments:
        server.reorder(arguments)
        print("OK order " + " ".join(arguments), flush=True)
    elif command == "duplicate" and len(arguments) == 2:
        server.set_reply_count(arguments[0], int(arguments[1]))
        print(f"OK duplicate {arguments[0]} {arguments[1]}", flush=True)
    elif command == "state" and len(arguments) <= 1:
        serials = arguments if arguments else server.order
        _print_state(server, serials)
    elif command == "displace" and len(arguments) == 4:
        server.displace(
            arguments[0], arguments[1], int(arguments[2]), arguments[3]
        )
        print(f"OK displaced {arguments[0]}", flush=True)
    elif command == "key" and len(arguments) == 4:
        server.emit_key(
            arguments[0], int(arguments[1]), int(arguments[2]), int(arguments[3])
        )
        print(
            f"OK key {arguments[0]} {arguments[1]} {arguments[2]} "
            f"{arguments[3]}",
            flush=True,
        )
    elif command == "grid" and len(arguments) == 1:
        _print_grid(server, arguments[0])
    elif command == "delta" and len(arguments) == 3:
        server.emit_delta(
            arguments[0], int(arguments[1]), int(arguments[2])
        )
        print(
            f"OK delta {arguments[0]} {arguments[1]} {arguments[2]}",
            flush=True,
        )
    elif command == "arc_key" and len(arguments) == 3:
        server.emit_arc_key(
            arguments[0], int(arguments[1]), int(arguments[2])
        )
        print(
            f"OK arc_key {arguments[0]} {arguments[1]} {arguments[2]}",
            flush=True,
        )
    elif command == "arc" and len(arguments) == 1:
        _print_arc(server, arguments[0])
    elif command == "reset" and not arguments:
        server.reset()
        print("OK reset", flush=True)
    elif command == "quit" and not arguments:
        return False
    else:
        raise ValueError("invalid_command")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_FAKE_PORT)
    parser.add_argument("--empty", action="store_true")
    parser.add_argument("--with-arc", type=int, choices=(2, 4))
    arguments = parser.parse_args()

    devices: tuple[Device, ...] = () if arguments.empty else DEFAULT_DEVICES
    if arguments.with_arc:
        devices = (*devices, default_arc(arguments.with_arc))
    try:
        with FakeSerialOSC(
            arguments.host,
            arguments.port,
            devices,
            spawn_device_servers=True,
        ) as server:
            print(f"READY {server.host} {server.port}", flush=True)
            _print_devices(server)
            running = True
            while running:
                readable, _, _ = select.select(
                    [*server.sockets, sys.stdin], [], []
                )
                for ready in readable:
                    if ready is sys.stdin:
                        continue
                    try:
                        server.serve_socket(ready)
                    except (OSCError, OSError) as error:
                        print(f"ERROR {error}", flush=True)
                if sys.stdin in readable:
                    line = sys.stdin.readline()
                    if not line:
                        break
                    try:
                        running = _command(server, line)
                    except (ValueError, OSError) as error:
                        print(f"ERROR {error}", flush=True)
    except (ValueError, OSError) as error:
        print(f"FATAL {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
