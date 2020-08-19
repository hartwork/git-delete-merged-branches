# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

import subprocess
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from parameterized import parameterized

from .._git import Git
from .._messenger import Messenger


class FindBranchesTest(TestCase):
    def test_find_branches_drops_head(self):
        existing_branches = ['remote1/HEAD', 'remote2/master']
        expected_branches = ['remote2/master']
        git = Git(Messenger(colorize=False), pretend=True, verbose=False)
        command_output_to_inject = ('\n'.join(existing_branches) + '\n').encode('utf-8')
        assert isinstance(command_output_to_inject, bytes)

        with patch.object(subprocess, 'check_output', return_value=command_output_to_inject):
            actual_branches = git._find_branches()

        self.assertEqual(actual_branches, expected_branches)


class OutputBytesToLinesTest(TestCase):
    @parameterized.expand([
        (b'one\ntwo', ['one', 'two']),
        (b'one\ntwo\n', ['one', 'two']),
        (b'one\ntwo\n\n', ['one', 'two']),
        (b'', []),
        (b'\n', []),
        (b'\n\n', []),
    ])
    def test_trailing_newlines(self, output_bytes, extected_interpretation):
        self.assertEqual(Git._output_bytes_to_lines(output_bytes),
                         extected_interpretation)


class ExtractGitConfigTest(TestCase):
    def test_escapes(self):
        expected_config = {
            'z.singlequote': '\'',
            'z.doublequote': '"',
            'z.doublequote-doublequote': '""',
            'z.doublequote-doublequote-doublequote': '"""',
            'z.backlslash': '\\',
            'z.backlslash-n': '\\n',
            'z.backlslash-t': '\\t',
            'z.backlslash-b': '\\b',
            'z.backlslash-doublequote': '\\"',
            'z.backlslash-backlslash': '\\\\',
            'z.linefeed': '\n',
            'z.tab': '\t',
            'z.backspace': chr(8),
        }

        with TemporaryDirectory() as d:
            subprocess.call(['git', 'init'], cwd=d)
            git = Git(Messenger(colorize=False), pretend=False, verbose=False,
                      work_dir=d)
            for k, v in expected_config.items():
                git.set_config(k, v)
            actual_config = {
                k: v for k, v in git.extract_git_config().items()
                if k in expected_config
            }

        self.assertEqual(actual_config, expected_config)
