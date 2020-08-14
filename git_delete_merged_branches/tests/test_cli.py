# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

import sys
from io import StringIO
from unittest import TestCase
from unittest.mock import patch

from .._cli import _parse_command_line


class HelpOutputTest(TestCase):
    def test_help(self):
        with patch.object(sys, 'stdout', StringIO()) as mock_stdout, self.assertRaises(SystemExit):
            _parse_command_line(colorize=True, args=['--help'])
        self.assertIn('usage', mock_stdout.getvalue())
