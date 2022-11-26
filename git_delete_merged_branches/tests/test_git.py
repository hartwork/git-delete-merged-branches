# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later
import os
import subprocess
from tempfile import TemporaryDirectory
from textwrap import dedent
from unittest import TestCase
from unittest.mock import Mock, call, patch

from parameterized import parameterized

from .._git import Git
from .._messenger import Messenger
from .helpers import create_git, run_script


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


class FindBranchNamesTest(TestCase):

    def test(self):
        find_branches_lines = [
            'heads/b1',
            'heads/b2',
            'remotes/remote1/b3',
            'remotes/remote2/b1',
        ]
        expected = {'b1', 'b2', 'b3'}
        git = Git(messenger=Mock(), pretend=True, verbose=False)

        with patch.object(git, '_find_branches',
                          return_value=find_branches_lines) as find_branches_mock:
            actual = git.find_all_branch_names()

        self.assertEqual(actual, expected)
        self.assertEqual(find_branches_mock.call_args_list, [call(['--all'], strip_left=1)])


class FindWorkingTreeBranchesTest(TestCase):

    def test_find_branches_drops_head(self):
        expected_branches = [None, 'branch-arrow-shift', 'refactor-layout-window']
        git = Git(Messenger(colorize=False), pretend=True, verbose=False)
        command_output_to_inject = dedent("""
            worktree /tmp/tmp.mgTEbE434g/pymux
            HEAD 493723318912cb44b1a3e47ba3fbc0e50b2a8f5c
            detached

            worktree /tmp/tmp.mgTEbE434g/branch-arrow-shift
            HEAD 3f66e62b9de4b2251c7f9afad6c516dc5a30ec67
            branch refs/heads/branch-arrow-shift

            worktree /tmp/tmp.mgTEbE434g/refactor-layout-window
            HEAD 3f66e62b9de4b2251c7f9afad6c516dc5a30ec67
            branch refs/heads/refactor-layout-window

        """).encode('utf-8')  # with two trialing newlines like Git would do
        assert isinstance(command_output_to_inject, bytes)

        with patch.object(subprocess, 'check_output', return_value=command_output_to_inject):
            actual_branches = git.find_working_tree_branches()

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
        self.assertEqual(Git._output_bytes_to_lines(output_bytes), extected_interpretation)


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
            'z.empty': '',
        }

        mock_messenger = Mock()

        with TemporaryDirectory() as d:
            subprocess.call(['git', 'init'], cwd=d)
            git = Git(messenger=mock_messenger, pretend=False, verbose=True, work_dir=d)
            for k, v in expected_config.items():
                git.set_config(k, v)

            with open(os.path.join(d, '.git/config'), 'a') as f:
                f.write('\tname-without-assignment')  # GitHub issue #96

            actual_config = {
                k: v
                for k, v in git.extract_git_config().items() if k in expected_config
            }

        self.assertEqual(actual_config, expected_config)

        self.assertEqual(mock_messenger.tell_info.call_args_list, [
            call('Git config option \'z.name-without-assignment\' lacks assignment of a value.'),
        ])


class RemoteBranchCollidesWithATagTest(TestCase):

    def test_remote_branch_deletable_despite_existing_tag_with_the_same_name(self):
        setup_script = dedent("""\
            mkdir upstream

            pushd upstream
                git init
                git commit --allow-empty -m 'First commit'
                git tag -m '' 1.0.0
                git branch 1.0.0
            popd

            git clone upstream downstream
        """)

        with TemporaryDirectory() as d:
            run_script(setup_script, cwd=d)
            downstream_git = create_git(work_dir=os.path.join(d, 'downstream'))
            self.assertIn('origin/1.0.0', downstream_git.find_remote_branches_at('origin'))

            downstream_git.delete_remote_branches(['origin/1.0.0'], 'origin')

            self.assertNotIn('origin/1.0.0', downstream_git.find_remote_branches_at('origin'))
