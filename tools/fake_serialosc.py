#!/usr/bin/env python3
"""Small, dependency-free SerialOSC workbench for development.

The simulator speaks the discovery and per-device system messages used by this
project. It never opens a serial device and refuses SerialOSC's live port 12002.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
import select
import shlex
import socket
import struct
import sys
from typing import Iterable


LIVE_SERIALOSC_PORT = 12002
DEFAULT_FAKE_PORT = 12012


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


DEFAULT_DEVICES = (
    Device("m100", "monome 128", 17001, 16, 8),
    Device("m200", "monome 256", 17002, 16, 16),
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

    def __init__(self, device: Device, host: str = "127.0.0.1") -> None:
        if device.port < 0 or device.port > 65535:
            raise ValueError("invalid_device_port")
        if (device.width is None) != (device.height is None):
            raise ValueError("incomplete_device_size")
        if device.width is not None and (
            device.width < 1 or device.height is None or device.height < 1
        ):
            raise ValueError("invalid_device_size")

        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((host, device.port))
        self.host, actual_port = self.socket.getsockname()
        self.device = replace(device, port=actual_port)
        self.destination_host = "127.0.0.1"
        self.destination_port = 0
        self.prefix = "/monome"
        self.rotation = 0

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

    def handle_packet(self, packet: bytes) -> None:
        address, arguments = decode_message(packet)
        if address == "/sys/info":
            target = self._info_target(
                arguments, self.destination_host, self.destination_port
            )
            if target is not None:
                self._send_info(target)
        elif address == "/sys/host":
            self.destination_host = self._string(arguments, "invalid_sys_host")
        elif address == "/sys/port":
            self.destination_port = self._port(arguments, allow_zero=True)
        elif address == "/sys/prefix":
            prefix = self._string(arguments, "invalid_sys_prefix")
            if not prefix.startswith("/"):
                raise OSCError("invalid_sys_prefix")
            self.prefix = prefix
        elif address == "/sys/rotation":
            rotation = self._port(arguments, allow_zero=True)
            if rotation not in (0, 90, 180, 270):
                raise OSCError("invalid_sys_rotation")
            self.rotation = rotation
        else:
            raise OSCError("unsupported_device_message")

    def serve_once(self, timeout: float = 0.1) -> bool:
        readable, _, _ = select.select([self.socket], [], [], timeout)
        if not readable:
            return False
        packet, _ = self.socket.recvfrom(65535)
        self.handle_packet(packet)
        return True

    def set_destination(self, host: str, port: int, prefix: str) -> None:
        if not host or port < 0 or port > 65535 or not prefix.startswith("/"):
            raise ValueError("invalid_destination")
        self.destination_host = host
        self.destination_port = port
        self.prefix = prefix


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

        try:
            for device in devices:
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
        readable, _, _ = select.select(self.sockets, [], [], timeout)
        if not readable:
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

    def _notify_once(self, address: str, serial: str) -> None:
        if self.notify_target is None:
            return
        target = self.notify_target
        self.notify_target = None
        self._send(target, address, serial)

    def add(self, device: Device) -> None:
        resolved = self._add_device(device)
        self._notify_once("/serialosc/add", resolved.serial)

    def remove(self, serial: str) -> None:
        if serial not in self.devices:
            raise ValueError("unknown_device")
        del self.devices[serial]
        self.order.remove(serial)
        self.reply_counts.pop(serial, None)
        endpoint = self.device_servers.pop(serial, None)
        if endpoint:
            endpoint.close()
        self._notify_once("/serialosc/remove", serial)

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
        for device in DEFAULT_DEVICES:
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


def _print_devices(server: FakeSerialOSC) -> None:
    for serial in server.order:
        device = server.devices[serial]
        print(f'DEVICE {device.serial} "{device.model}" {device.port}', flush=True)


def _print_state(server: FakeSerialOSC, serials: Iterable[str]) -> None:
    for serial in serials:
        host, port, prefix = server.device_state(serial)
        print(f'STATE {serial} "{host}" {port} "{prefix}"', flush=True)


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
            "state [SERIAL] | displace SERIAL HOST PORT PREFIX | reset | quit",
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
    arguments = parser.parse_args()

    devices: Iterable[Device] = () if arguments.empty else DEFAULT_DEVICES
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
