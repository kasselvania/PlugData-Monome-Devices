#!/usr/bin/env python3
"""Print a read-only snapshot of every device advertised by live SerialOSC."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import socket
import time

from fake_serialosc import bind_callback, decode_message, encode_message


@dataclass(frozen=True)
class DiscoveredDevice:
    serial: str
    model: str
    server_port: int


@dataclass(frozen=True)
class DeviceState:
    serial: str
    model: str
    server_host: str
    server_port: int
    destination_host: str
    destination_port: int
    prefix: str
    rotation: int
    width: int | None
    height: int | None


def _receive_batch(
    callback: socket.socket,
    timeout_seconds: float,
    quiet_seconds: float = 0.05,
) -> list[tuple[str, tuple[object, ...]]]:
    deadline = time.monotonic() + timeout_seconds
    messages: list[tuple[str, tuple[object, ...]]] = []

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return messages
        callback.settimeout(min(quiet_seconds if messages else remaining, remaining))
        try:
            packet, _ = callback.recvfrom(65535)
        except socket.timeout:
            if messages:
                return messages
            continue
        messages.append(decode_message(packet))


def discover(
    callback: socket.socket,
    server: tuple[str, int],
    timeout_seconds: float,
) -> list[DiscoveredDevice]:
    host, port = callback.getsockname()
    callback.sendto(encode_message("/serialosc/list", host, port), server)

    devices: dict[str, DiscoveredDevice] = {}
    order: list[str] = []
    for address, atoms in _receive_batch(callback, timeout_seconds):
        if address != "/serialosc/device" or len(atoms) != 3:
            raise ValueError(f"unexpected_discovery_reply {address}")
        serial, model, server_port = atoms
        if (
            not isinstance(serial, str)
            or not serial
            or not isinstance(model, str)
            or not model
            or not isinstance(server_port, int)
            or server_port < 1
            or server_port > 65535
        ):
            raise ValueError("invalid_discovery_reply")
        device = DiscoveredDevice(serial, model, server_port)
        previous = devices.get(serial)
        if previous is not None and previous != device:
            raise ValueError(f"conflicting_device_identity {serial}")
        if previous is None:
            order.append(serial)
        devices[serial] = device

    return [devices[serial] for serial in order]


def probe(
    callback: socket.socket,
    device: DiscoveredDevice,
    server_host: str,
    timeout_seconds: float,
) -> DeviceState:
    callback_host, callback_port = callback.getsockname()
    callback.sendto(
        encode_message("/sys/info", callback_host, callback_port),
        (server_host, device.server_port),
    )

    values: dict[str, tuple[object, ...]] = {}
    for address, atoms in _receive_batch(callback, timeout_seconds):
        if not address.startswith("/sys/"):
            raise ValueError(f"unexpected_info_reply {address}")
        previous = values.get(address)
        if previous is not None and previous != atoms:
            raise ValueError(f"conflicting_info_reply {device.serial} {address}")
        values[address] = atoms

    required = ("/sys/id", "/sys/host", "/sys/port", "/sys/prefix", "/sys/rotation")
    missing = [address for address in required if address not in values]
    if missing:
        raise ValueError(
            f"incomplete_info {device.serial} {' '.join(missing)}"
        )

    serial_atoms = values["/sys/id"]
    host_atoms = values["/sys/host"]
    port_atoms = values["/sys/port"]
    prefix_atoms = values["/sys/prefix"]
    rotation_atoms = values["/sys/rotation"]
    size_atoms = values.get("/sys/size")

    if serial_atoms != (device.serial,):
        raise ValueError(f"identity_mismatch {device.serial}")
    if len(host_atoms) != 1 or not isinstance(host_atoms[0], str):
        raise ValueError(f"invalid_destination_host {device.serial}")
    if (
        len(port_atoms) != 1
        or not isinstance(port_atoms[0], int)
        or port_atoms[0] < 0
        or port_atoms[0] > 65535
    ):
        raise ValueError(f"invalid_destination_port {device.serial}")
    if (
        len(prefix_atoms) != 1
        or not isinstance(prefix_atoms[0], str)
        or not prefix_atoms[0].startswith("/")
    ):
        raise ValueError(f"invalid_prefix {device.serial}")
    if rotation_atoms not in ((0,), (90,), (180,), (270,)):
        raise ValueError(f"invalid_rotation {device.serial}")

    width: int | None = None
    height: int | None = None
    if size_atoms is not None:
        if (
            len(size_atoms) != 2
            or not all(isinstance(value, int) for value in size_atoms)
            or any(value < 0 for value in size_atoms)
            or ((size_atoms[0] == 0) != (size_atoms[1] == 0))
        ):
            raise ValueError(f"invalid_size {device.serial}")
        width, height = size_atoms

    return DeviceState(
        serial=device.serial,
        model=device.model,
        server_host=server_host,
        server_port=device.server_port,
        destination_host=host_atoms[0],
        destination_port=port_atoms[0],
        prefix=prefix_atoms[0],
        rotation=rotation_atoms[0],
        width=width,
        height=height,
    )


def snapshot(
    callback: socket.socket,
    serialosc_server: tuple[str, int],
    timeout_seconds: float,
) -> list[DeviceState]:
    devices = discover(callback, serialosc_server, timeout_seconds)
    return [
        probe(callback, device, serialosc_server[0], timeout_seconds)
        for device in devices
    ]


def _format_size(state: DeviceState) -> str:
    if state.width is None or state.height is None:
        return "unknown"
    return f"{state.width}x{state.height}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--callback-port", type=int, default=17851)
    parser.add_argument("--serialosc-host", default="127.0.0.1")
    parser.add_argument("--serialosc-port", type=int, default=12002)
    parser.add_argument("--timeout", type=float, default=0.5)
    parser.add_argument("--json", action="store_true")
    arguments = parser.parse_args()

    if arguments.timeout <= 0:
        parser.error("--timeout must be positive")

    try:
        with bind_callback(arguments.host, arguments.callback_port) as callback:
            states = snapshot(
                callback,
                (arguments.serialosc_host, arguments.serialosc_port),
                arguments.timeout,
            )
    except (OSError, ValueError) as error:
        print(f"FATAL {error}")
        return 1

    if arguments.json:
        print(json.dumps([asdict(state) for state in states], sort_keys=True))
        return 0

    if not states:
        print("NO_DEVICES")
        return 0

    for state in states:
        print(
            f"{state.serial} | {state.model} | "
            f"server {state.server_host}:{state.server_port} | "
            f"destination {state.destination_host}:{state.destination_port} | "
            f"prefix {state.prefix} | rotation {state.rotation} | "
            f"size {_format_size(state)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
