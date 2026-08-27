#!/usr/bin/env python3

from __future__ import annotations

import argparse
import socket


CONTROL_PORT = 17900
COMMANDS = (
    "a_select",
    "a_session",
    "a_grid",
    "b_select",
    "b_session",
    "b_grid",
    "discovery",
)


def control_port(value: str) -> int:
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("control port must be an integer") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError(
            "control port must be between 1 and 65535"
        )
    return port


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Send one local control command to a Monome Grid live patch."
    )
    parser.add_argument(
        "--port",
        type=control_port,
        default=CONTROL_PORT,
        help=f"local Pd control port (default: {CONTROL_PORT})",
    )
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument("arguments", nargs="+")
    args = parser.parse_args()

    tokens = (args.command, *args.arguments)
    if any(";" in token or "\n" in token or "\r" in token for token in tokens):
        parser.error("command tokens may not contain FUDI delimiters")

    message = (" ".join(tokens) + ";\n").encode("utf-8")
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(message, ("127.0.0.1", args.port))

    print("sent:", " ".join(tokens))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
