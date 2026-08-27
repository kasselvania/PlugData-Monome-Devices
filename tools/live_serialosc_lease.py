#!/usr/bin/env python3
"""Probe live SerialOSC lease state or run one bounded expiry test."""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
import secrets
import socket
import time

from fake_serialosc import bind_callback, decode_message, encode_message
from live_serialosc_state import (
    DiscoveredDevice,
    DeviceState,
    _receive_batch,
    discover,
    probe,
)


LEASE_VERSION = 1
MIN_TTL_MS = 1000
MAX_TEST_TTL_MS = 10000
DEFAULT_CALLBACK_PORT = 17852
DEFAULT_PREFIX = "/monome-expiry-test"


@dataclass(frozen=True)
class LeaseState:
    version: int
    serial: str
    mode: str
    destination_host: str
    destination_port: int
    prefix: str
    remaining_ms: int
    owner: bool


@dataclass(frozen=True)
class ExpiryResult:
    device: DeviceState
    claimed: LeaseState
    released: LeaseState
    lost_observed: bool


def _parse_lease_state(
    atoms: tuple[object, ...], expected_serial: str
) -> LeaseState:
    if len(atoms) != 8:
        raise ValueError("invalid_lease_state_shape")
    version, serial, mode, host, port, prefix, remaining_ms, owner = atoms
    if version != LEASE_VERSION:
        raise ValueError(f"unsupported_lease_version {version}")
    if serial != expected_serial:
        raise ValueError(f"lease_identity_mismatch {expected_serial} {serial}")
    if mode not in ("free", "legacy", "leased"):
        raise ValueError(f"invalid_lease_mode {mode}")
    if not isinstance(host, str) or not host:
        raise ValueError("invalid_lease_host")
    if not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("invalid_lease_port")
    if not isinstance(prefix, str) or not prefix.startswith("/"):
        raise ValueError("invalid_lease_prefix")
    if not isinstance(remaining_ms, int) or remaining_ms < 0:
        raise ValueError("invalid_lease_remaining")
    if owner not in (0, 1):
        raise ValueError("invalid_lease_owner")
    if (mode == "free") != (port == 0):
        raise ValueError("inconsistent_lease_port")
    if mode != "leased" and (remaining_ms != 0 or owner != 0):
        raise ValueError("inconsistent_lease_liveness")
    return LeaseState(
        version=version,
        serial=serial,
        mode=mode,
        destination_host=host,
        destination_port=port,
        prefix=prefix,
        remaining_ms=remaining_ms,
        owner=bool(owner),
    )


def query_lease(
    callback: socket.socket,
    device: DiscoveredDevice,
    server_host: str,
    timeout_seconds: float,
    token: str | None = None,
) -> LeaseState | None:
    callback_host, callback_port = callback.getsockname()
    arguments: tuple[object, ...]
    if token is None:
        arguments = (callback_host, callback_port)
    else:
        arguments = (token, callback_host, callback_port)
    callback.sendto(
        encode_message("/sys/lease/info", *arguments),
        (server_host, device.server_port),
    )

    state: LeaseState | None = None
    for address, atoms in _receive_batch(callback, timeout_seconds):
        if address != "/sys/lease/state":
            raise ValueError(f"unexpected_lease_reply {address}")
        current = _parse_lease_state(atoms, device.serial)
        if state is not None and state != current:
            raise ValueError(f"conflicting_lease_state {device.serial}")
        state = current
    return state


def lease_snapshot(
    callback: socket.socket,
    serialosc_server: tuple[str, int],
    timeout_seconds: float,
) -> list[tuple[DeviceState, LeaseState | None]]:
    devices = discover(callback, serialosc_server, timeout_seconds)
    result: list[tuple[DeviceState, LeaseState | None]] = []
    for device in devices:
        device_state = probe(
            callback, device, serialosc_server[0], timeout_seconds
        )
        result.append(
            (
                device_state,
                query_lease(
                    callback, device, serialosc_server[0], timeout_seconds
                ),
            )
        )
    return result


def _await_grant(
    callback: socket.socket,
    token: str,
    ttl_ms: int,
    timeout_seconds: float,
) -> None:
    granted = False
    for address, atoms in _receive_batch(callback, timeout_seconds):
        if address == "/sys/lease/granted" and atoms == (token, ttl_ms):
            granted = True
        elif address == "/sys/lease/rejected" and len(atoms) == 2:
            reply_token, reason = atoms
            if reply_token == token:
                raise ValueError(f"lease_rejected {reason}")
        else:
            raise ValueError(f"unexpected_acquire_reply {address}")
    if not granted:
        raise ValueError("lease_grant_timeout")


def _send_test_pattern(
    callback: socket.socket,
    endpoint: tuple[str, int],
    state: DeviceState,
    prefix: str,
    level: int,
    arc_rings: int | None,
) -> None:
    if state.width is not None and state.height is not None:
        if arc_rings is not None:
            raise ValueError("arc_rings_supplied_for_grid")
        for y_offset in range(0, state.height, 8):
            for x_offset in range(0, state.width, 8):
                callback.sendto(
                    encode_message(
                        prefix + "/grid/led/level/map",
                        x_offset,
                        y_offset,
                        *([level] * 64),
                    ),
                    endpoint,
                )
        return

    if arc_rings not in (2, 4):
        raise ValueError("arc_requires_explicit_2_or_4_rings")
    for ring in range(arc_rings):
        callback.sendto(
            encode_message(
                prefix + "/ring/map", ring, *([level] * 64)
            ),
            endpoint,
        )


def _observe_expiry(
    callback: socket.socket,
    token: str,
    ttl_ms: int,
    timeout_seconds: float,
) -> bool:
    deadline = time.monotonic() + (ttl_ms / 1000) + timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        callback.settimeout(remaining)
        try:
            packet, _ = callback.recvfrom(65535)
        except socket.timeout:
            return False
        address, atoms = decode_message(packet)
        if address == "/sys/lease/lost" and atoms == (token, "expired"):
            return True
        raise ValueError(f"unexpected_expiry_reply {address}")


def expiry_test(
    callback: socket.socket,
    serialosc_server: tuple[str, int],
    serial: str,
    timeout_seconds: float,
    ttl_ms: int,
    level: int,
    arc_rings: int | None,
    report: Callable[[str], None] | None = None,
) -> ExpiryResult:
    devices = discover(callback, serialosc_server, timeout_seconds)
    matches = [device for device in devices if device.serial == serial]
    if len(matches) != 1:
        raise ValueError(f"device_not_found {serial}")
    device = matches[0]
    device_state = probe(
        callback, device, serialosc_server[0], timeout_seconds
    )
    token = "expiry-" + secrets.token_hex(24)
    before = query_lease(
        callback, device, serialosc_server[0], timeout_seconds, token
    )
    if before is None:
        raise ValueError("lease_unsupported")
    if before.mode != "free" or before.destination_port != 0:
        raise ValueError(
            f"lease_not_free {before.mode} {before.destination_port}"
        )

    callback_host, callback_port = callback.getsockname()
    endpoint = (serialosc_server[0], device.server_port)
    callback.sendto(
        encode_message(
            "/sys/lease/acquire",
            token,
            callback_host,
            callback_port,
            DEFAULT_PREFIX,
            ttl_ms,
        ),
        endpoint,
    )
    _await_grant(callback, token, ttl_ms, timeout_seconds)
    claimed = query_lease(
        callback, device, serialosc_server[0], timeout_seconds, token
    )
    if (
        claimed is None
        or claimed.mode != "leased"
        or not claimed.owner
        or claimed.destination_port != callback_port
        or claimed.prefix != DEFAULT_PREFIX
    ):
        raise ValueError("lease_claim_readback_failed")
    if report is not None:
        report(
            f"LEASE_GRANTED {device_state.serial} {claimed.remaining_ms}ms"
        )

    _send_test_pattern(
        callback,
        endpoint,
        device_state,
        DEFAULT_PREFIX,
        level,
        arc_rings,
    )
    if report is not None:
        report("PATTERN_SENT")
        report("WAITING_FOR_EXPIRY")
    lost_observed = _observe_expiry(
        callback, token, ttl_ms, timeout_seconds
    )
    released = query_lease(
        callback, device, serialosc_server[0], timeout_seconds, token
    )
    if (
        released is None
        or released.mode != "free"
        or released.destination_port != 0
        or released.owner
    ):
        raise ValueError("lease_expiry_readback_failed")
    return ExpiryResult(
        device=device_state,
        claimed=claimed,
        released=released,
        lost_observed=lost_observed,
    )


def _print_probe(
    entries: list[tuple[DeviceState, LeaseState | None]],
) -> None:
    if not entries:
        print("NO_DEVICES")
        return
    for device, lease in entries:
        if lease is None:
            print(f"{device.serial} | {device.model} | lease unsupported")
            continue
        print(
            f"{device.serial} | {device.model} | lease v{lease.version} "
            f"{lease.mode} | destination "
            f"{lease.destination_host}:{lease.destination_port} | "
            f"prefix {lease.prefix} | remaining {lease.remaining_ms} ms | "
            f"owner {int(lease.owner)}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--callback-port", type=int, default=DEFAULT_CALLBACK_PORT)
    parser.add_argument("--serialosc-host", default="127.0.0.1")
    parser.add_argument("--serialosc-port", type=int, default=12002)
    parser.add_argument("--timeout", type=float, default=0.5)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("probe", help="Read device and lease state only.")
    expiry = subparsers.add_parser(
        "expiry-test",
        help="Acquire one free device, light it, omit renew/release, and verify expiry.",
    )
    expiry.add_argument("--serial", required=True)
    expiry.add_argument("--ttl-ms", type=int, default=3000)
    expiry.add_argument("--level", type=int, default=4)
    expiry.add_argument("--arc-rings", type=int, choices=(2, 4))
    arguments = parser.parse_args()

    if arguments.timeout <= 0:
        parser.error("--timeout must be positive")
    if arguments.command == "expiry-test":
        if not MIN_TTL_MS <= arguments.ttl_ms <= MAX_TEST_TTL_MS:
            parser.error(
                f"--ttl-ms must be between {MIN_TTL_MS} and {MAX_TEST_TTL_MS}"
            )
        if not 1 <= arguments.level <= 15:
            parser.error("--level must be between 1 and 15")

    server = (arguments.serialosc_host, arguments.serialosc_port)
    try:
        with bind_callback(arguments.host, arguments.callback_port) as callback:
            if arguments.command == "probe":
                _print_probe(lease_snapshot(callback, server, arguments.timeout))
            else:
                result = expiry_test(
                    callback,
                    server,
                    arguments.serial,
                    arguments.timeout,
                    arguments.ttl_ms,
                    arguments.level,
                    arguments.arc_rings,
                    lambda message: print(message, flush=True),
                )
                print(
                    "LOST_OBSERVED "
                    + ("yes" if result.lost_observed else "no")
                )
                print(
                    f"EXPIRY_VERIFIED {result.released.mode} "
                    f"port={result.released.destination_port}"
                )
    except (OSError, ValueError) as error:
        print(f"FATAL {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
