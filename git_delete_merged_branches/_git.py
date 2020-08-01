# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

import subprocess
import sys
from collections import OrderedDict
from typing import List, Optional


class Git:
    _GIT = 'git'

    def __init__(self, ask, pretend, verbose):
        self._ask = ask
        self._verbose = verbose
        self._pretend = pretend

    def _subprocess_check_output(self, argv, is_write):
        pretend = is_write and self._pretend
        if self._verbose:
            epilog = '   # skipped due to --pretend' if pretend else ''
            display_argv = [a for a in argv if not a.startswith('--format=')]
            print(f'# {" ".join(display_argv)}{epilog}', file=sys.stderr)
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

    def _find_branches(self, extra_argv=None):
        argv = [
            self._GIT,
            'branch', '--format=%(refname:lstrip=2)',
        ]
        if extra_argv is not None:
            argv += extra_argv
        output_bytes = self._subprocess_check_output(argv, is_write=False)
        lines = self._output_bytes_to_lines(output_bytes)
        return [line for line in lines if not line.endswith('/HEAD')]

    def find_local_branches(self):
        return self._find_branches()

    def find_all_branches(self):
        return self._find_branches(['--all'])

    def find_current_branch(self) -> Optional[str]:
        branch_names = self._find_branches(['--show-current'])
        if not branch_names:
            return None
        assert len(branch_names) == 1
        return branch_names[0]

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

    def delete_local_branches(self, branch_names):
        if not branch_names:
            return
        argv = [self._GIT, 'branch', '--delete'] + list(branch_names)
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
