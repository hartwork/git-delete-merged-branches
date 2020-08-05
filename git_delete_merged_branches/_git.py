# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

import subprocess
from collections import OrderedDict
from typing import List, Optional


class Git:
    _GIT = 'git'

    def __init__(self, messenger, ask, pretend, verbose):
        self._messenger = messenger
        self._ask = ask
        self._verbose = verbose
        self._pretend = pretend

    def _subprocess_check_output(self, argv, is_write):
        pretend = is_write and self._pretend
        if self._verbose:
            comment = 'skipped due to --dry-run' if pretend else ''
            display_argv = [a for a in argv if not a.startswith('--format=')]
            self._messenger.tell_command(display_argv, comment)
        if pretend:
            return bytes()
        return subprocess.check_output(argv)

    @classmethod
    def _output_bytes_to_lines(cls, output_bytes) -> List[str]:
        text = output_bytes.decode('utf-8').rstrip()
        if not text:  # protect against this: ''.split('\n') -> ['']
            return []
        return text.split('\n')

    def extract_git_config(self):
        argv = [self._GIT, 'config', '--list']
        output_bytes = self._subprocess_check_output(argv, is_write=False)
        config_lines = self._output_bytes_to_lines(output_bytes)
        git_config = OrderedDict()
        for line in config_lines:
            equal_sign_index = line.index('=')
            if equal_sign_index < 1:
                continue
            key, value = line[:equal_sign_index], line[equal_sign_index + 1:]
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
        return [line for line in lines if not line.endswith('/HEAD')]

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
        argv = ['git', 'rev-parse', '--symbolic-full-name', 'HEAD']
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

        self._subprocess_check_output(argv, is_write=True)

    def delete_remote_branches(self, branch_names, remote_name):
        if not branch_names:
            return
        remote_prefix = f'{remote_name}/'
        remote_branches_to_delete = [
            remote_slash_branch[len(remote_prefix):]
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

    def checkout(self, branch_name: str) -> None:
        argv = [self._GIT, 'checkout', branch_name]
        self._subprocess_check_output(argv, is_write=True)

    def pull_ff_only(self) -> None:
        argv = [self._GIT, 'pull', '--ff-only']
        self._subprocess_check_output(argv, is_write=True)

    def has_uncommitted_changes(self) -> bool:
        try:
            base_argv = [self._GIT, 'diff', '--exit-code', '--quiet', ]
            for extra_argv in ([], ['--cached']):
                argv = base_argv + extra_argv
                self._subprocess_check_output(argv, is_write=False)
            return False
        except subprocess.CalledProcessError as e:
            if e.returncode == 1:
                return True
            raise

    def cherry(self, target_branch, topic_branch) -> List[str]:
        argv = [self._GIT, 'cherry', target_branch, topic_branch]
        output_bytes = self._subprocess_check_output(argv, is_write=False)
        return self._output_bytes_to_lines(output_bytes)
