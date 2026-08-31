#!/usr/bin/env python3

from __future__ import annotations

import socket
import unittest

from tools.live_arc_events import EVENT_PORT, build_parser, receive_events


class LiveArcEventsTests(unittest.TestCase):
    def test_receiver_captures_exact_signed_encoder_deltas(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
            receiver.bind(("127.0.0.1", 0))
            port = receiver.getsockname()[1]

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                sender.sendto(b"arc_delta 0 4;\n", ("127.0.0.1", port))
                sender.sendto(b"arc_delta 3 -2;\n", ("127.0.0.1", port))

            events = list(receive_events(receiver, 2, 1.0))

        self.assertEqual(events, ["arc_delta 0 4", "arc_delta 3 -2"])

    def test_default_port_is_the_arc_event_port(self) -> None:
        self.assertEqual(build_parser().parse_args([]).port, EVENT_PORT)
        self.assertEqual(EVENT_PORT, 17911)


if __name__ == "__main__":
    unittest.main(verbosity=2)
