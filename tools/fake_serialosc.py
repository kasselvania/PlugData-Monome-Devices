#!/usr/bin/env python3
"""Small, dependency-free SerialOSC discovery simulator for development.

The simulator speaks only the discovery messages used by this project. It
never opens a serial device and refuses to bind SerialOSC's live port 12002.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
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


DEFAULT_DEVICES = (
    Device("m100", "monome 128", 17001),
    Device("m200", "monome 256", 17002),
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


class FakeSerialOSC:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = DEFAULT_FAKE_PORT,
        devices: Iterable[Device] = DEFAULT_DEVICES,
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

        for device in devices:
            self._validate_device(device)
            if device.serial in self.devices:
                raise ValueError("duplicate_device_serial")
            self.devices[device.serial] = device
            self.order.append(device.serial)

    @staticmethod
    def _validate_device(device: Device) -> None:
        if not device.serial or not device.model:
            raise ValueError("invalid_device")
        if device.port < 1 or device.port > 65535:
            raise ValueError("invalid_device_port")

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
        readable, _, _ = select.select([self.socket], [], [], timeout)
        if not readable:
            return False
        packet, _ = self.socket.recvfrom(65535)
        self.handle_packet(packet)
        return True

    def _notify_once(self, address: str, serial: str) -> None:
        if self.notify_target is None:
            return
        target = self.notify_target
        self.notify_target = None
        self._send(target, address, serial)

    def add(self, device: Device) -> None:
        self._validate_device(device)
        if device.serial in self.devices:
            raise ValueError("duplicate_device_serial")
        self.devices[device.serial] = device
        self.order.append(device.serial)
        self._notify_once("/serialosc/add", device.serial)

    def remove(self, serial: str) -> None:
        if serial not in self.devices:
            raise ValueError("unknown_device")
        del self.devices[serial]
        self.order.remove(serial)
        self.reply_counts.pop(serial, None)
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
        self.devices = {device.serial: device for device in DEFAULT_DEVICES}
        self.order = [device.serial for device in DEFAULT_DEVICES]
        self.reply_counts = {}


def _print_devices(server: FakeSerialOSC) -> None:
    for serial in server.order:
        device = server.devices[serial]
        print(f'DEVICE {device.serial} "{device.model}" {device.port}', flush=True)


def _command(server: FakeSerialOSC, line: str) -> bool:
    words = shlex.split(line)
    if not words:
        return True
    command, arguments = words[0], words[1:]

    if command == "help":
        print(
            'COMMANDS: devices | add SERIAL "MODEL" PORT | remove SERIAL | '
            "order SERIAL... | duplicate SERIAL COUNT | reset | quit",
            flush=True,
        )
    elif command == "devices" and not arguments:
        _print_devices(server)
    elif command == "add" and len(arguments) == 3:
        server.add(Device(arguments[0], arguments[1], int(arguments[2])))
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
        with FakeSerialOSC(arguments.host, arguments.port, devices) as server:
            print(f"READY {server.host} {server.port}", flush=True)
            _print_devices(server)
            running = True
            while running:
                readable, _, _ = select.select([server.socket, sys.stdin], [], [])
                if server.socket in readable:
                    try:
                        packet, _ = server.socket.recvfrom(65535)
                        server.handle_packet(packet)
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
