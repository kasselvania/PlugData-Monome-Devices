#!/usr/bin/env python3

from __future__ import annotations

import unittest

from tools.serialosc_monitor import build_parser


class SerialOSCMonitorTests(unittest.TestCase):
    def test_default_callback_port_is_fresh_for_each_run(self) -> None:
        self.assertEqual(build_parser().parse_args([]).callback_port, 0)

    def test_explicit_callback_port_is_preserved(self) -> None:
        self.assertEqual(
            build_parser().parse_args(["--callback-port", "17850"]).callback_port,
            17850,
        )


if __name__ == "__main__":
    unittest.main()
