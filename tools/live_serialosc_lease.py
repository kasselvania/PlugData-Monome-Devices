#!/usr/bin/env python3
"""Probe live SerialOSC leases or run bounded lifecycle tests."""

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
DEFAULT_PREFIX = "/monome-lease-test"


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


@dataclass(frozen=True)
class RenewReleaseResult:
    device: DeviceState
    claimed: LeaseState
    maintained: LeaseState
    released: LeaseState
    renewals: int


@dataclass(frozen=True)
class _ClaimedTestLease:
    discovered: DiscoveredDevice
    device: DeviceState
    token: str
    endpoint: tuple[str, int]
    claimed: LeaseState


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


def _await_renewal(
    callback: socket.socket,
    token: str,
    ttl_ms: int,
    timeout_seconds: float,
) -> None:
    renewed = False
    for address, atoms in _receive_batch(callback, timeout_seconds):
        if address == "/sys/lease/renewed" and atoms == (token, ttl_ms):
            renewed = True
        elif address == "/sys/lease/rejected" and len(atoms) == 2:
            reply_token, reason = atoms
            if reply_token == token:
                raise ValueError(f"lease_renew_rejected {reason}")
        else:
            raise ValueError(f"unexpected_renew_reply {address}")
    if not renewed:
        raise ValueError("lease_renew_timeout")


def _await_release(
    callback: socket.socket,
    token: str,
    timeout_seconds: float,
) -> None:
    released = False
    for address, atoms in _receive_batch(callback, timeout_seconds):
        if address == "/sys/lease/released" and atoms == (token,):
            released = True
        elif address == "/sys/lease/rejected" and len(atoms) == 2:
            reply_token, reason = atoms
            if reply_token == token:
                raise ValueError(f"lease_release_rejected {reason}")
        else:
            raise ValueError(f"unexpected_release_reply {address}")
    if not released:
        raise ValueError("lease_release_timeout")


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


def _claim_test_lease(
    callback: socket.socket,
    serialosc_server: tuple[str, int],
    serial: str,
    timeout_seconds: float,
    ttl_ms: int,
    takeover_legacy: bool,
    token_label: str,
    report: Callable[[str], None] | None = None,
) -> _ClaimedTestLease:
    devices = discover(callback, serialosc_server, timeout_seconds)
    matches = [device for device in devices if device.serial == serial]
    if len(matches) != 1:
        raise ValueError(f"device_not_found {serial}")
    device = matches[0]
    device_state = probe(
        callback, device, serialosc_server[0], timeout_seconds
    )
    token = token_label + "-" + secrets.token_hex(24)
    before = query_lease(
        callback, device, serialosc_server[0], timeout_seconds, token
    )
    if before is None:
        raise ValueError("lease_unsupported")
    if before.mode == "leased":
        raise ValueError(
            f"lease_not_free {before.mode} {before.destination_port}"
        )
    if before.mode == "legacy" and not takeover_legacy:
        raise ValueError(
            f"legacy_takeover_required {before.destination_port}"
        )
    if before.mode == "free" and before.destination_port != 0:
        raise ValueError("inconsistent_free_destination")

    callback_host, callback_port = callback.getsockname()
    endpoint = (serialosc_server[0], device.server_port)
    acquire_path = (
        "/sys/lease/takeover"
        if before.mode == "legacy"
        else "/sys/lease/acquire"
    )
    callback.sendto(
        encode_message(
            acquire_path,
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
    return _ClaimedTestLease(
        discovered=device,
        device=device_state,
        token=token,
        endpoint=endpoint,
        claimed=claimed,
    )


def expiry_test(
    callback: socket.socket,
    serialosc_server: tuple[str, int],
    serial: str,
    timeout_seconds: float,
    ttl_ms: int,
    level: int,
    arc_rings: int | None,
    takeover_legacy: bool = False,
    report: Callable[[str], None] | None = None,
) -> ExpiryResult:
    active = _claim_test_lease(
        callback,
        serialosc_server,
        serial,
        timeout_seconds,
        ttl_ms,
        takeover_legacy,
        "expiry",
        report,
    )

    _send_test_pattern(
        callback,
        active.endpoint,
        active.device,
        DEFAULT_PREFIX,
        level,
        arc_rings,
    )
    if report is not None:
        report("PATTERN_SENT")
        report("WAITING_FOR_EXPIRY")
    lost_observed = _observe_expiry(
        callback, active.token, ttl_ms, timeout_seconds
    )
    released = query_lease(
        callback,
        active.discovered,
        serialosc_server[0],
        timeout_seconds,
        active.token,
    )
    if (
        released is None
        or released.mode != "free"
        or released.destination_port != 0
        or released.owner
    ):
        raise ValueError("lease_expiry_readback_failed")
    return ExpiryResult(
        device=active.device,
        claimed=active.claimed,
        released=released,
        lost_observed=lost_observed,
    )


def renew_release_test(
    callback: socket.socket,
    serialosc_server: tuple[str, int],
    serial: str,
    timeout_seconds: float,
    ttl_ms: int,
    renew_ms: int,
    hold_ms: int,
    level: int,
    arc_rings: int | None,
    takeover_legacy: bool = False,
    report: Callable[[str], None] | None = None,
) -> RenewReleaseResult:
    active = _claim_test_lease(
        callback,
        serialosc_server,
        serial,
        timeout_seconds,
        ttl_ms,
        takeover_legacy,
        "renew-release",
        report,
    )
    _send_test_pattern(
        callback,
        active.endpoint,
        active.device,
        DEFAULT_PREFIX,
        level,
        arc_rings,
    )
    if report is not None:
        report("PATTERN_SENT")
        report("RENEWING_BEYOND_INITIAL_TTL")

    callback_host, callback_port = callback.getsockname()
    started = time.monotonic()
    deadline = started + (hold_ms / 1000)
    next_renewal = started + (renew_ms / 1000)
    renewals = 0
    while next_renewal < deadline:
        time.sleep(max(0.0, next_renewal - time.monotonic()))
        callback.sendto(
            encode_message(
                "/sys/lease/renew",
                active.token,
                ttl_ms,
                callback_host,
                callback_port,
            ),
            active.endpoint,
        )
        _await_renewal(callback, active.token, ttl_ms, timeout_seconds)
        renewals += 1
        if report is not None:
            report(f"LEASE_RENEWED {renewals}")
        next_renewal += renew_ms / 1000
    time.sleep(max(0.0, deadline - time.monotonic()))

    maintained = query_lease(
        callback,
        active.discovered,
        serialosc_server[0],
        timeout_seconds,
        active.token,
    )
    if (
        maintained is None
        or maintained.mode != "leased"
        or not maintained.owner
        or maintained.destination_port != callback_port
        or maintained.prefix != DEFAULT_PREFIX
    ):
        raise ValueError("lease_renew_readback_failed")
    if report is not None:
        report(
            f"INITIAL_TTL_SURVIVED {maintained.remaining_ms}ms"
        )

    callback.sendto(
        encode_message(
            "/sys/lease/release",
            active.token,
            callback_host,
            callback_port,
        ),
        active.endpoint,
    )
    _await_release(callback, active.token, timeout_seconds)
    released = query_lease(
        callback,
        active.discovered,
        serialosc_server[0],
        timeout_seconds,
        active.token,
    )
    if (
        released is None
        or released.mode != "free"
        or released.destination_port != 0
        or released.owner
    ):
        raise ValueError("lease_release_readback_failed")
    if report is not None:
        report("LEASE_RELEASED")
    return RenewReleaseResult(
        device=active.device,
        claimed=active.claimed,
        maintained=maintained,
        released=released,
        renewals=renewals,
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
    expiry.add_argument(
        "--takeover-legacy",
        action="store_true",
        help="Explicitly permit replacing a verified legacy destination.",
    )
    renew_release = subparsers.add_parser(
        "renew-release-test",
        help="Renew one lease beyond its initial TTL, then release it.",
    )
    renew_release.add_argument("--serial", required=True)
    renew_release.add_argument("--ttl-ms", type=int, default=6000)
    renew_release.add_argument("--renew-ms", type=int, default=2000)
    renew_release.add_argument("--hold-ms", type=int, default=8000)
    renew_release.add_argument("--level", type=int, default=4)
    renew_release.add_argument("--arc-rings", type=int, choices=(2, 4))
    renew_release.add_argument(
        "--takeover-legacy",
        action="store_true",
        help="Explicitly permit replacing a verified legacy destination.",
    )
    arguments = parser.parse_args()

    if arguments.timeout <= 0:
        parser.error("--timeout must be positive")
    if arguments.command in ("expiry-test", "renew-release-test"):
        if not MIN_TTL_MS <= arguments.ttl_ms <= MAX_TEST_TTL_MS:
            parser.error(
                f"--ttl-ms must be between {MIN_TTL_MS} and {MAX_TEST_TTL_MS}"
            )
        if not 1 <= arguments.level <= 15:
            parser.error("--level must be between 1 and 15")
    if arguments.command == "renew-release-test":
        if not 0 < arguments.renew_ms < arguments.ttl_ms:
            parser.error("--renew-ms must be positive and less than --ttl-ms")
        if arguments.hold_ms <= arguments.ttl_ms:
            parser.error("--hold-ms must be greater than --ttl-ms")

    server = (arguments.serialosc_host, arguments.serialosc_port)
    try:
        with bind_callback(arguments.host, arguments.callback_port) as callback:
            if arguments.command == "probe":
                _print_probe(lease_snapshot(callback, server, arguments.timeout))
            elif arguments.command == "expiry-test":
                result = expiry_test(
                    callback,
                    server,
                    arguments.serial,
                    arguments.timeout,
                    arguments.ttl_ms,
                    arguments.level,
                    arguments.arc_rings,
                    takeover_legacy=arguments.takeover_legacy,
                    report=lambda message: print(message, flush=True),
                )
                print(
                    "LOST_OBSERVED "
                    + ("yes" if result.lost_observed else "no")
                )
                print(
                    f"EXPIRY_VERIFIED {result.released.mode} "
                    f"port={result.released.destination_port}"
                )
            else:
                result = renew_release_test(
                    callback,
                    server,
                    arguments.serial,
                    arguments.timeout,
                    arguments.ttl_ms,
                    arguments.renew_ms,
                    arguments.hold_ms,
                    arguments.level,
                    arguments.arc_rings,
                    takeover_legacy=arguments.takeover_legacy,
                    report=lambda message: print(message, flush=True),
                )
                print(
                    f"RENEW_RELEASE_VERIFIED renewals={result.renewals} "
                    f"{result.released.mode} "
                    f"port={result.released.destination_port}"
                )
    except (OSError, ValueError) as error:
        print(f"FATAL {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
