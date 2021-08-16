# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

import os
import subprocess
from collections import OrderedDict
from typing import List, Optional

from ._metadata import APP


class GitException(Exception):
    pass


class CheckoutFailed(GitException):
    pass


class PullFailed(GitException):
    pass


class Git:
    _GIT = 'git'
    _GIT_ENCODING = 'utf-8'

    _APP_EMAIL = f'{APP}@localhost'
    _ARBITRARY_FIXED_DATETIME = '2005-12-21T00:00:00+00:00'  # release date of Git 1.0.0
    _COMMIT_ENVIRON = {
        'GIT_AUTHOR_DATE': _ARBITRARY_FIXED_DATETIME,
        'GIT_AUTHOR_EMAIL': _APP_EMAIL,
        'GIT_AUTHOR_NAME': APP,
        'GIT_COMMITTER_DATE': _ARBITRARY_FIXED_DATETIME,
        'GIT_COMMITTER_EMAIL': _APP_EMAIL,
        'GIT_COMMITTER_NAME': APP,
    }

    def __init__(self, messenger, pretend, verbose, work_dir=None):
        self._messenger = messenger
        self._verbose = verbose
        self._pretend = pretend
        self._working_directory = work_dir

    def _wrap_subprocess(self, subprocess_function, argv, is_write, pretend_result, env):
        pretend = is_write and self._pretend
        if self._verbose:
            comment = 'skipped due to --dry-run' if pretend else ''
            display_argv = [a for a in argv if not a.startswith('--format=')]
            self._messenger.tell_command(display_argv, comment)
        if pretend:
            return pretend_result
        return subprocess_function(argv, cwd=self._working_directory, env=env)

    def _subprocess_check_output(self, argv, is_write, env=None):
        return self._wrap_subprocess(subprocess.check_output, argv=argv,
                                     is_write=is_write, pretend_result=bytes(), env=env)

    def _subprocess_check_call(self, argv, is_write, env=None):
        return self._wrap_subprocess(subprocess.check_call, argv=argv,
                                     is_write=is_write, pretend_result=0, env=env)

    @classmethod
    def _output_bytes_to_lines(cls, output_bytes) -> List[str]:
        text = output_bytes.decode(cls._GIT_ENCODING).rstrip()
        if not text:  # protect against this: ''.split('\n') -> ['']
            return []
        return text.split('\n')

    def extract_git_config(self):
        argv = [self._GIT, 'config', '--list', '--null']
        output_bytes = self._subprocess_check_output(argv, is_write=False)
        key_newline_value_list = [chunk.decode(self._GIT_ENCODING)
                                  for chunk in output_bytes.split(b'\0')]
        git_config = OrderedDict()
        for key_newline_value in key_newline_value_list:
            if not key_newline_value:
                continue
            key, value = key_newline_value.split('\n', 1)
            git_config[key] = value
        return git_config

    def find_remotes(self):
        argv = [self._GIT, 'remote']
        output_bytes = self._subprocess_check_output(argv, is_write=False)
        return self._output_bytes_to_lines(output_bytes)

    def _find_branches(self, extra_argv=None) -> List[str]:
        argv = [
            self._GIT,
            'branch', '--format=%(refname:lstrip=2)',
        ]
        if extra_argv is not None:
            argv += extra_argv
        output_bytes = self._subprocess_check_output(argv, is_write=False)
        lines = self._output_bytes_to_lines(output_bytes)
        return [line for line in lines
                if not line.endswith('/HEAD') and 'HEAD detached at' not in line]

    def find_local_branches(self) -> List[str]:
        return self._find_branches()

    def find_all_branches(self) -> List[str]:
        return self._find_branches(['--all'])

    def find_remote_branches_at(self, remote_name) -> List[str]:
        assert remote_name
        extra_argv = ['--remote', '--list', f'{remote_name}/*']
        return self._find_branches(extra_argv)

    def find_current_branch(self) -> Optional[str]:
        # Note: Avoiding "git branch --show-current" of Git >=2.22.0
        #       to keep Git 2.17.1 of Ubuntu 18.04 in the boat, for now.
        argv = [self._GIT, 'rev-parse', '--symbolic-full-name', 'HEAD']
        output_bytes = self._subprocess_check_output(argv, is_write=False)
        lines = self._output_bytes_to_lines(output_bytes)
        assert len(lines) == 1

        expected_prefix = 'refs/heads/'
        reference = lines[0]  # 'HEAD' when detached, else 'refs/heads/<branch>'
        if not reference.startswith(expected_prefix):
            return None  # detached head
        return reference[len(expected_prefix):]

    def _get_merged_branches_for(self, target_branch: str, remote: bool):
        extra_argv = []
        if remote:
            extra_argv.append('--remote')
        extra_argv += [
            '--merged', target_branch,
        ]
        merged_branches = self._find_branches(extra_argv)
        return (branch for branch in merged_branches if branch != target_branch)

    def find_merged_local_branches_for(self, branch_name):
        return self._get_merged_branches_for(branch_name, remote=False)

    def find_merged_remote_branches_for(self, remote_name, branch_name):
        return self._get_merged_branches_for(f'{remote_name}/{branch_name}', remote=True)

    def delete_local_branches(self, branch_names, force=False):
        if not branch_names:
            return

        argv = [self._GIT, 'branch', '--delete']
        if force:
            argv.append('--force')
        argv += sorted(branch_names)

        self._subprocess_check_call(argv, is_write=True)

    def delete_remote_branches(self, branch_names, remote_name):
        if not branch_names:
            return
        remote_prefix = f'{remote_name}/'
        remote_branches_to_delete = [
            'refs/heads/' + remote_slash_branch[len(remote_prefix):]
            for remote_slash_branch
            in branch_names
            if remote_slash_branch.startswith(remote_prefix)
        ]
        if not remote_branches_to_delete:
            return
        argv = [
            self._GIT,
            'push',
            '--delete',
            '--force-with-lease',
            remote_name,
        ] + remote_branches_to_delete

        self._subprocess_check_output(argv, is_write=True)

    def set_config(self, key, value):
        argv = [self._GIT, 'config']

        if value is None:
            argv += ['--unset', key]
        else:
            argv += [key, value]

        self._subprocess_check_output(argv, is_write=True)

    def update_and_prune_remote(self, remote_name: str) -> None:
        argv = [self._GIT, 'remote', 'update', '--prune', remote_name]
        self._subprocess_check_output(argv, is_write=True)

    def checkout(self, committish: str) -> None:
        argv = [self._GIT, 'checkout', '-q']
        argv.append(committish)
        try:
            self._subprocess_check_output(argv, is_write=True)
        except subprocess.CalledProcessError as e:
            if e.returncode == 1:
                raise CheckoutFailed
            raise

    def pull_ff_only(self) -> None:
        argv = [self._GIT, 'pull', '--ff-only']
        try:
            self._subprocess_check_output(argv, is_write=True)
        except subprocess.CalledProcessError as e:
            if e.returncode == 1:
                raise PullFailed
            raise

    def _has_changes(self, extra_argv: Optional[List[str]] = None) -> bool:
        argv = [self._GIT, 'diff', '--exit-code', '--quiet']
        if extra_argv:
            argv += extra_argv

        try:
            self._subprocess_check_output(argv, is_write=False)
            return False
        except subprocess.CalledProcessError as e:
            if e.returncode == 1:
                return True
            raise

    def has_staged_changes(self) -> bool:
        return self._has_changes(['--cached'])

    def has_uncommitted_changes(self) -> bool:
        if self._has_changes():
            return True
        return self.has_staged_changes()

    def cherry(self, target_branch, topic_branch) -> List[str]:
        argv = [self._GIT, 'cherry', target_branch, topic_branch]
        output_bytes = self._subprocess_check_output(argv, is_write=False)
        return self._output_bytes_to_lines(output_bytes)

    def has_unpushed_commits_on(self, branch, with_regard_to):
        cherry_lines = self.cherry(with_regard_to, branch)
        return any(line.startswith('+') for line in cherry_lines)

    def commit_tree(self, message: str, parent_committish: str, tree: str) -> str:
        argv = [self._GIT, 'commit-tree', '-m', message, '-p', parent_committish, tree]
        env = os.environ.copy()
        env.update(self._COMMIT_ENVIRON)
        # Note: Command "git commit-tree" does write to the repository but it does
        #       not switch branches, move HEAD or delete things; that's why it
        #       it is considered "not writing" (``is_write=False``) here and
        #       will be performed even when ``--dry-run``/``self._pretend`` is active.
        output_bytes = self._subprocess_check_output(argv, env=env, is_write=False)
        lines = self._output_bytes_to_lines(output_bytes)
        assert len(lines) == 1
        return lines[0]

    def merge_base(self, target_branch, topic_branch) -> str:
        argv = [self._GIT, 'merge-base', target_branch, topic_branch]
        output_bytes = self._subprocess_check_output(argv, is_write=False)
        lines = self._output_bytes_to_lines(output_bytes)
        assert len(lines) == 1
        return lines[0]
