#!/usr/bin/env python3
"""Capture machine-readable key events from the live Grid workbench."""

from __future__ import annotations

import argparse
import socket
import time
from collections.abc import Iterator


EVENT_PORT = 17910


def event_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("event port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(
            "event port must be between 1 and 65535"
        )
    return port


def positive_count(value: str) -> int:
    try:
        count = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("count must be an integer") from exc
    if count < 1:
        raise argparse.ArgumentTypeError("count must be positive")
    return count


def positive_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timeout must be a number") from exc
    if timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be positive")
    return timeout


def decode_fudi_messages(packet: bytes) -> tuple[str, ...]:
    try:
        text = packet.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("event packet is not UTF-8") from exc

    if not text.rstrip().endswith(";"):
        raise ValueError("event packet is missing its FUDI delimiter")

    messages = tuple(
        message.strip()
        for message in text.split(";")
        if message.strip()
    )
    if not messages:
        raise ValueError("event packet contains no messages")
    return messages


def receive_events(
    callback: socket.socket,
    count: int,
    timeout_seconds: float,
) -> Iterator[str]:
    deadline = time.monotonic() + timeout_seconds
    received = 0

    while received < count:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"received {received} of {count} events")
        callback.settimeout(remaining)
        try:
            packet, _ = callback.recvfrom(65535)
        except socket.timeout as exc:
            raise TimeoutError(f"received {received} of {count} events") from exc

        for message in decode_fudi_messages(packet):
            yield message
            received += 1
            if received == count:
                return


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument(
        "--port",
        type=event_port,
        default=EVENT_PORT,
        help=f"loopback event port (default: {EVENT_PORT})",
    )
    parser.add_argument(
        "--count",
        type=positive_count,
        default=2,
        help="number of events to capture (default: 2)",
    )
    parser.add_argument(
        "--timeout",
        type=positive_timeout,
        default=30.0,
        help="overall capture timeout in seconds (default: 30)",
    )
    arguments = parser.parse_args()

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as callback:
            callback.bind((arguments.host, arguments.port))
            host, port = callback.getsockname()
            print(f"READY {host}:{port}", flush=True)
            for event in receive_events(
                callback,
                arguments.count,
                arguments.timeout,
            ):
                print(event, flush=True)
    except (OSError, TimeoutError, ValueError) as error:
        print(f"FATAL {error}", flush=True)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
