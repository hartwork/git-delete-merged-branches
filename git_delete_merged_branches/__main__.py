# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

import argparse
import os
import re
import sys
import traceback
from argparse import RawDescriptionHelpFormatter
from functools import partial, reduce
from operator import and_
from signal import SIGINT
from subprocess import CalledProcessError
from textwrap import dedent
from typing import List, Optional, Set, Tuple

import colorama

from ._argparse_color import add_color_to_formatter_class
from ._confirm import Confirmation
from ._git import Git
from ._messenger import Messenger
from ._metadata import APP, DESCRIPTION, VERSION
from ._multiselect import multiselect


class _DmbException(Exception):
    pass


class _NoSuchBranchException(_DmbException):
    def __init__(self, branch_name):
        super().__init__(f'There is no branch {branch_name!r}.')


class _NoSuchRemoteException(_DmbException):
    def __init__(self, remote_name):
        super().__init__(f'There is no remote {remote_name!r}.')


class _ZeroMergeTargetsException(_DmbException):
    def __init__(self):
        super().__init__('One or more existing target branch is required.')


class _TooFewOptionsAvailable(_DmbException):
    pass


class _GitRepositoryWithoutBranches(_DmbException):
    """
    Exception for the time between "git init" and the first "git commit"
    where "git branch" will tell us that there are no branches
    """
    def __init__(self):
        super().__init__('This Git repository does not have any branches.')


class _DeleteMergedBranches:
    _CONFIG_KEY_CONFIGURED = 'dmb.configured'
    _CONFIG_VALUE_TRUE = 'true'
    _PATTERN_REMOTE_ENABLED = '^remote.(?P<name>[^.]+).dmb-enabled$'
    _PATTERN_BRANCH_REQUIRED = '^branch.(?P<name>[^.]+).dmb-required$'
    _FORMAT_REMOTE_ENABLED = 'remote.{name}.dmb-enabled'
    _FORMAT_BRANCH_REQUIRED = 'branch.{name}.dmb-required'

    def __init__(self, git, messenger, confirmation, effort_level):
        self._confirmation = confirmation
        self._messenger = messenger
        self._git = git
        self._effort_using_git_cherry = effort_level >= 2

    def _interactively_edit_list(self, description, valid_names, old_names, format,
                                 min_selection_count):
        if len(valid_names) < min_selection_count:
            raise _TooFewOptionsAvailable

        heading = f'== Configure {APP} for this repository =='
        help = ('(Press [Space] to toggle selection, [Enter]/[Return] to accept'
                ', [Ctrl]+[C] to quit.)')
        heading = f'{heading}\n{description}\n\n{help}'

        old_names = set(old_names)
        initial_selection = [i for i, name in enumerate(valid_names) if name in old_names]
        if valid_names:
            new_names = set(multiselect(valid_names, initial_selection,
                                        heading, min_selection_count))
        else:
            new_names = set()
        assert len(new_names) >= min_selection_count
        names_to_remove = old_names - new_names
        names_to_add = new_names - old_names

        for names, new_value in (
                (names_to_remove, None),
                (names_to_add, self._CONFIG_VALUE_TRUE)):
            for name in names:
                key = format.format(name=name)
                self._git.set_config(key, new_value)

    def _configure_required_branches(self, git_config):
        try:
            self._interactively_edit_list('[1/2] For a branch to be considered fully merged'
                                          ', which other branches must it have been merged to?',
                                          self._git.find_local_branches(),
                                          self.find_required_branches(git_config),
                                          self._FORMAT_BRANCH_REQUIRED, min_selection_count=1)
        except _TooFewOptionsAvailable:
            raise _GitRepositoryWithoutBranches

    def _configure_enabled_remotes(self, git_config):
        self._interactively_edit_list('[2/2] Which remotes (if any) do you want to enable'
                                      ' deletion of merged branches for?',
                                      self._git.find_remotes(),
                                      self.find_enabled_remotes(git_config),
                                      self._FORMAT_REMOTE_ENABLED, min_selection_count=0)

    def _configure(self, git_config):
        self._configure_required_branches(git_config)
        self._configure_enabled_remotes(git_config)
        self._git.set_config(self._CONFIG_KEY_CONFIGURED, self._CONFIG_VALUE_TRUE)

    @classmethod
    def _is_configured(cls, git_config):
        return git_config.get(cls._CONFIG_KEY_CONFIGURED) == cls._CONFIG_VALUE_TRUE

    def ensure_configured(self, force_reconfiguration):
        git_config = self._git.extract_git_config()
        if force_reconfiguration or not self._is_configured(git_config):
            self._configure(git_config)
            git_config = self._git.extract_git_config()
        assert self._is_configured(git_config)
        return git_config

    @classmethod
    def _filter_git_config(cls, git_config, pattern):
        matcher = re.compile(pattern)
        matched_names = []
        for key, value in git_config.items():
            match = matcher.match(key)
            if match and value == cls._CONFIG_VALUE_TRUE:
                matched_names.append(match.group('name'))
        return matched_names

    @classmethod
    def find_required_branches(cls, git_config):
        return cls._filter_git_config(git_config, cls._PATTERN_BRANCH_REQUIRED)

    @classmethod
    def find_enabled_remotes(cls, git_config):
        return cls._filter_git_config(git_config, cls._PATTERN_REMOTE_ENABLED)

    def _find_branches_merged_using_git_branch_merged(self, required_target_branches,
                                                      remote_name: Optional[str]) -> Set[str]:
        if remote_name is None:
            find_branches_that_were_merged_into = self._git.find_merged_local_branches_for
        else:
            find_branches_that_were_merged_into = partial(
                self._git.find_merged_remote_branches_for, remote_name)

        if len(required_target_branches) == 1:
            target_branch = next(iter(required_target_branches))
            branches_merged_to_all_required_targets = set(
                find_branches_that_were_merged_into(target_branch)
            )
        else:
            branches_merged_to_all_required_targets = reduce(and_, (
                set(find_branches_that_were_merged_into(target_branch))
                for target_branch in required_target_branches))

        return branches_merged_to_all_required_targets

    def _find_branches_merged_using_git_cherry(self, required_target_branches,
                                               candidate_branches) -> Set[str]:
        assert required_target_branches

        if not candidate_branches:
            return set()

        branches_merged_to_all_required_targets = set()

        for topic_branch in sorted(candidate_branches):
            assert topic_branch not in required_target_branches

            for target_branch in sorted(required_target_branches):
                cherry_lines = self._git.cherry(target_branch, topic_branch)
                defacto_merged_into_target = all(line.startswith('-') for line in cherry_lines)
                if not defacto_merged_into_target:
                    break
            else:  # i.e. no break happened above
                branches_merged_to_all_required_targets.add(topic_branch)

        return branches_merged_to_all_required_targets

    def _find_branches_merged_to_all_targets_for_single_remote(self, required_target_branches,
                                                               remote_name: Optional[str]
                                                               ) -> Tuple[Set[str], Set[str]]:
        truly_merged_branches = (
            self._find_branches_merged_using_git_branch_merged(required_target_branches,
                                                               remote_name=remote_name)
        )

        if self._effort_using_git_cherry:
            if remote_name is None:
                all_branches_at_remote = set(self._git.find_local_branches())
            else:
                all_branches_at_remote = set(self._git.find_remote_branches_at(remote_name))
            if remote_name is not None:
                required_target_branches = {f'{remote_name}/{branch_name}'
                                            for branch_name in required_target_branches}
            branches_to_inspect_using_git_cherry = (all_branches_at_remote
                                                    - required_target_branches
                                                    - truly_merged_branches)
            defacto_merged_branches = self._find_branches_merged_using_git_cherry(
                required_target_branches, branches_to_inspect_using_git_cherry)
        else:
            defacto_merged_branches = set()

        return (truly_merged_branches, defacto_merged_branches)

    def _delete_local_merged_branches_for(self, required_target_branches):
        truly_merged, defacto_merged = (
            self._find_branches_merged_to_all_targets_for_single_remote(
                required_target_branches, remote_name=None))

        current_branch = self._git.find_current_branch()
        for branches_to_delete in (truly_merged, defacto_merged):
            if current_branch in branches_to_delete:
                self._messenger.tell_info(f'Skipped branch {current_branch!r} '
                                          'because it is currently checked out.')
                branches_to_delete.remove(current_branch)

        local_branches_to_delete = truly_merged | defacto_merged

        if not local_branches_to_delete:
            self._messenger.tell_info('No local branches deleted.')
            return

        description = (f'You are about to delete {len(local_branches_to_delete)}'
                       ' local branch(es):\n'
                       + '\n'.join(f'  - {name}' for name in sorted(local_branches_to_delete))
                       + '\n\nDelete?')
        if not self._confirmation.confirmed(description):
            return

        self._git.delete_local_branches(truly_merged)
        self._git.delete_local_branches(defacto_merged, force=True)

        self._messenger.tell_info(f'{len(local_branches_to_delete)} local branch(es) deleted.')

    def _delete_remote_merged_branches_for(self, required_target_branches, remote_name,
                                           all_branch_names: Set[str]):
        if not all((f'{remote_name}/{branch_name}' in all_branch_names)
                   for branch_name in required_target_branches):
            self._messenger.tell_info('Skipped remote {remote_name!r} '
                                      'as it does not have all required branches.')
            return

        truly_merged, defacto_merged = self._find_branches_merged_to_all_targets_for_single_remote(
            required_target_branches, remote_name=remote_name)
        remote_branches_to_delete = [
            b for b in (truly_merged | defacto_merged) if b.startswith(f'{remote_name}/')]

        if not remote_branches_to_delete:
            self._messenger.tell_info('No remote branches deleted.')
            return

        description = (f'You are about to delete {len(remote_branches_to_delete)} '
                       'remote branch(es):\n'
                       + '\n'.join(f'  - {name}' for name in sorted(remote_branches_to_delete))
                       + '\n\nDelete?')
        if not self._confirmation.confirmed(description):
            return

        self._git.delete_remote_branches(remote_branches_to_delete, remote_name)
        self._messenger.tell_info(f'{len(remote_branches_to_delete)} remote branch(es) deleted.')

    def refresh_remotes(self, enabled_remotes):
        sorted_remotes = sorted(set(enabled_remotes))
        if not sorted_remotes:
            return

        description = (f'Do you want to run "git remote update --prune"'
                       f' for {len(sorted_remotes)} remote(s):\n'
                       + '\n'.join(f'  - {name}' for name in sorted_remotes)
                       + '\n\nUpdate?')
        if not self._confirmation.confirmed(description):
            return

        for remote_name in sorted_remotes:
            self._git.update_and_prune_remote(remote_name)

    def refresh_target_branches(self, required_target_branches):
        sorted_branches = sorted(set(required_target_branches))
        if not sorted_branches:
            return

        initial_branch = self._git.find_current_branch()
        if initial_branch is None:
            self._messenger.tell_info('Skipped refreshing branches because of detached HEAD.')
            return

        if self._git.has_uncommitted_changes():
            self._messenger.tell_info('Skipped refreshing branches due to uncommitted changes.')
            return

        description = (f'Do you want to run "git pull --ff-only"'
                       f' for {len(sorted_branches)} branches(s):\n'
                       + '\n'.join(f'  - {name}' for name in sorted_branches)
                       + '\n\nPull?')
        if not self._confirmation.confirmed(description):
            return

        needs_a_switch_back = False
        try:
            for branch_name in sorted_branches:
                if branch_name != initial_branch:
                    self._git.checkout(branch_name)
                    needs_a_switch_back = True
                self._git.pull_ff_only()
        finally:
            if needs_a_switch_back:
                self._git.checkout(initial_branch)

    def delete_merged_branches(self, required_target_branches, enabled_remotes):
        self._delete_local_merged_branches_for(required_target_branches)
        all_branch_names = set(self._git.find_all_branches())
        for remote_name in enabled_remotes:
            self._delete_remote_merged_branches_for(required_target_branches, remote_name,
                                                    all_branch_names)

    def determine_required_target_branches(self, git_config: dict,
                                           required_target_branches: List[str]):
        existing_branches = set(self._git.find_local_branches())
        if required_target_branches:
            required_target_branches_set = set(required_target_branches)
            invalid_branches = required_target_branches_set - existing_branches
            if invalid_branches:
                raise _NoSuchBranchException(required_target_branches[0])
        else:
            required_target_branches_set = (
                set(_DeleteMergedBranches.find_required_branches(git_config))
                & existing_branches
            )

        if not required_target_branches_set:
            raise _ZeroMergeTargetsException

        return required_target_branches_set

    def determine_enabled_remotes(self, git_config: dict, enabled_remotes: List[str]):
        existing_remotes = set(self._git.find_remotes())
        if enabled_remotes:
            enabled_remotes_set = set(enabled_remotes)
            invalid_remotes = enabled_remotes_set - existing_remotes
            if invalid_remotes:
                raise _NoSuchRemoteException(enabled_remotes[0])
            return enabled_remotes_set
        else:
            return (set(_DeleteMergedBranches.find_enabled_remotes(git_config))
                    & existing_remotes)


def _parse_command_line(colorize: bool, args=None):
    _EPILOG = dedent(f"""\
        Software libre licensed under GPL v3 or later.
        Brought to you by Sebastian Pipping <sebastian@pipping.org>.

        Please report bugs at https://github.com/hartwork/{APP}.  Thank you!
    """)

    if args is None:
        args = sys.argv[1:]

    formatter_class = RawDescriptionHelpFormatter
    if colorize:
        formatter_class = add_color_to_formatter_class(formatter_class)

    parser = argparse.ArgumentParser(prog='git-delete-merged-branches', add_help=False,
                                     description=DESCRIPTION, epilog=_EPILOG,
                                     formatter_class=formatter_class)

    modes = parser.add_argument_group('modes').add_mutually_exclusive_group()
    modes.add_argument('--configure', dest='force_reconfiguration', action='store_true',
                       help=f'configure {APP} and exit (without processing any branches)')
    modes.add_argument('--help', '-h', action='help', help='show this help message and exit')
    modes.add_argument('--version', action='version', version='%(prog)s ' + VERSION)

    scope = parser.add_argument_group('scope')
    scope.add_argument('--remote', '-r', metavar='REMOTE', dest='enabled_remotes', default=[],
                       action='append',
                       help='process the given remote (instead of the remotes that are'
                            ' configured for this repository); can be passed multiple times')

    rules = parser.add_argument_group('rules')
    rules.add_argument('--branch', '-b', metavar='BRANCH', dest='required_target_branches',
                       default=[], action='append',
                       help='require the given branch as a merge target (instead of what is'
                            ' configured for this repository); can be passed multiple times')
    rules.add_argument('--effort', metavar='LEVEL', dest='effort_level',
                       type=int, default=2, choices=[1, 2],
                       help='level of effort to put into finding merged branches; '
                            'level 1 uses nothing but "git branch --merged", '
                            'level 2 adds use of "git cherry"; (default level: %(default)d)')

    switches = parser.add_argument_group('flags')
    switches.add_argument('--debug', dest='debug', action='store_true',
                          help='enable debugging output')
    switches.add_argument('--dry-run', '-n', dest='pretend', action='store_true',
                          help='perform a trial run with no changes made')
    switches.add_argument('--verbose', '-v', dest='verbose', action='store_true',
                          help='enable verbose output')
    switches.add_argument('--yes', '-y', dest='ask', default=True, action='store_false',
                          help='do not ask for confirmation, assume reply "yes"')

    return parser.parse_args(args)


def _innermost_main(config, messenger):
    git = Git(messenger, ask=config.ask, pretend=config.pretend, verbose=config.verbose)
    confirmation = Confirmation(messenger, ask=config.ask)
    dmb = _DeleteMergedBranches(git, messenger, confirmation, config.effort_level)

    git_config = dmb.ensure_configured(config.force_reconfiguration)
    if config.force_reconfiguration:
        return

    required_target_branches = dmb.determine_required_target_branches(
        git_config, config.required_target_branches)
    enabled_remotes = dmb.determine_enabled_remotes(git_config, config.enabled_remotes)

    dmb.refresh_remotes(enabled_remotes)
    dmb.refresh_target_branches(required_target_branches)
    dmb.delete_merged_branches(required_target_branches, enabled_remotes)


def _inner_main():
    colorize = 'NO_COLOR' not in os.environ
    if colorize:
        colorama.init()

    messenger = Messenger(colorize=colorize)

    config = _parse_command_line(colorize=colorize)
    try:
        _innermost_main(config, messenger)
    except CalledProcessError as e:
        # Produce more human-friendly output than str(e)
        message = f"Command '{' '.join(e.cmd)}' returned non-zero exit status {e.returncode}."
        messenger.tell_error(message)
        sys.exit(1)
    except Exception as e:
        if config.debug:
            traceback.print_exc()
        messenger.tell_error(str(e))
        sys.exit(1)


def main():
    try:
        _inner_main()
    except KeyboardInterrupt:
        sys.exit(128 + SIGINT)


if __name__ == '__main__':
    main()
