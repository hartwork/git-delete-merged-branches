# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

from unittest import TestCase

from parameterized import parameterized

from .._shell import escape_for_shell_display


class ShellEscapingTest(TestCase):
    @parameterized.expand([
        ('', "''"),
        ('one', 'one'),
        ('one two', "'one two'"),
        ("tick'tick'$", '"tick\'tick\'\\$"'),
    ])
    def test(self, text, expected_escaped_text):
        self.assertEqual(escape_for_shell_display(text), expected_escaped_text)
