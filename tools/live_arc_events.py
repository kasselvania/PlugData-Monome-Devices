#!/usr/bin/env python3
"""Capture machine-readable encoder events from the live Arc workbench."""

from __future__ import annotations

import argparse
import pathlib
import socket
import sys


TOOLS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from live_grid_events import (  # noqa: E402
    event_port,
    positive_count,
    positive_timeout,
    receive_events,
)


EVENT_PORT = 17911


def build_parser() -> argparse.ArgumentParser:
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
    return parser


def main() -> int:
    arguments = build_parser().parse_args()

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
