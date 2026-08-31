#!/usr/bin/env python3

from __future__ import annotations

import argparse
import socket
import unittest

from tools.live_grid_events import (
    decode_fudi_messages,
    event_port,
    positive_count,
    positive_timeout,
    receive_events,
)


class LiveGridEventsTests(unittest.TestCase):
    def test_receiver_captures_exact_press_and_release(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
            receiver.bind(("127.0.0.1", 0))
            port = receiver.getsockname()[1]

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                sender.sendto(b"a_key 0 0 1;\n", ("127.0.0.1", port))
                sender.sendto(b"a_key 0 0 0;\n", ("127.0.0.1", port))

            events = list(receive_events(receiver, 2, 1.0))

        self.assertEqual(events, ["a_key 0 0 1", "a_key 0 0 0"])

    def test_decoder_accepts_multiple_fudi_messages(self) -> None:
        self.assertEqual(
            decode_fudi_messages(b"a_key 1 2 1; a_key 1 2 0;\n"),
            ("a_key 1 2 1", "a_key 1 2 0"),
        )

    def test_decoder_rejects_invalid_packets(self) -> None:
        for packet in (b"a_key 0 0 1", b";\n", b"\xff;"):
            with self.subTest(packet=packet):
                with self.assertRaises(ValueError):
                    decode_fudi_messages(packet)

    def test_numeric_arguments_fail_closed(self) -> None:
        for value in ("0", "65536", "not-a-port"):
            with self.subTest(kind="port", value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    event_port(value)
        for validator in (positive_count, positive_timeout):
            for value in ("0", "-1", "not-a-number"):
                with self.subTest(validator=validator.__name__, value=value):
                    with self.assertRaises(argparse.ArgumentTypeError):
                        validator(value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
