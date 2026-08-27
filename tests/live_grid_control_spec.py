#!/usr/bin/env python3

from __future__ import annotations

import argparse
import socket
import sys
import unittest
from unittest import mock

from tools.live_grid_control import control_port, main


class LiveGridControlTests(unittest.TestCase):
    def test_custom_control_port_receives_fudi_command(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as receiver:
            receiver.bind(("127.0.0.1", 0))
            receiver.settimeout(1)
            port = receiver.getsockname()[1]

            argv = [
                "live_grid_control.py",
                "--port",
                str(port),
                "a_session",
                "probe",
            ]
            with mock.patch.object(sys, "argv", argv):
                self.assertEqual(main(), 0)

            message, _ = receiver.recvfrom(1024)

        self.assertEqual(message, b"a_session probe;\n")

    def test_control_port_accepts_udp_range_boundaries(self) -> None:
        self.assertEqual(control_port("1"), 1)
        self.assertEqual(control_port("65535"), 65535)

    def test_control_port_rejects_invalid_values(self) -> None:
        for value in ("0", "65536", "not-a-port"):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    control_port(value)


if __name__ == "__main__":
    unittest.main(verbosity=2)
