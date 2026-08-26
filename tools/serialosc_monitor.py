#!/usr/bin/env python3
"""Read-only live SerialOSC discovery monitor for physical acceptance."""

from __future__ import annotations

import argparse
import pathlib
import socket
import sys


TOOLS = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))

from fake_serialosc import bind_callback, decode_message, encode_message  # noqa: E402


def arm(callback: socket.socket, server: tuple[str, int]) -> None:
    host, port = callback.getsockname()
    callback.sendto(encode_message("/serialosc/notify", host, port), server)
    callback.sendto(encode_message("/serialosc/list", host, port), server)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--callback-port", type=int, default=17850)
    parser.add_argument("--serialosc-host", default="127.0.0.1")
    parser.add_argument("--serialosc-port", type=int, default=12002)
    arguments = parser.parse_args()

    server = (arguments.serialosc_host, arguments.serialosc_port)
    try:
        with bind_callback(arguments.host, arguments.callback_port) as callback:
            host, port = callback.getsockname()
            print(f"READY {host} {port} -> {server[0]}:{server[1]}", flush=True)
            arm(callback, server)
            while True:
                packet, _ = callback.recvfrom(65535)
                address, atoms = decode_message(packet)
                print(address, *atoms, flush=True)
                if address in ("/serialosc/add", "/serialosc/remove"):
                    arm(callback, server)
    except KeyboardInterrupt:
        print("STOPPED", flush=True)
        return 0
    except (OSError, ValueError) as error:
        print(f"FATAL {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
