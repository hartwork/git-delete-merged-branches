# Copyright (C) 2026 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

from unittest import TestCase

from parameterized import parameterized

from .._without import without


class WithoutTest(TestCase):
    A = "A"
    B = "B"
    C = "C"
    D = "D"

    @parameterized.expand(
        [
            ("empty container", [A, B], [], []),
            ("empty needle", [], [C, D], [C, D]),
            ("empty needle, empty container", [], [], []),
            ("no matches", [A, B], [C, D], [C, D]),
            ("whole container matched", [A, B], [A, B], []),
            ("whole container matched, multiple", [A, B], [A, B, A, B], []),
            ("needle head match", [A, B], [A, C, B], [A, C, B]),
            ("needle head match, followed by match", [A, B], [A, A, A, B], [A, A]),
            ("match at the start", [A, B], [A, B, C], [C]),
            ("match at the end", [A, B], [C, A, B], [C]),
            ("match in the middle", [A, B], [C, A, B, D], [C, D]),
            ("in between two matches", [A, B], [A, B, C, A, B], [C]),
            ("surrounding two matches", [A, B], [C, A, B, D, A, B, C], [C, D, C]),
        ]
    )
    def test(self, _label, needle, container, expected):
        self.assertEqual(without(needle, container), expected)
