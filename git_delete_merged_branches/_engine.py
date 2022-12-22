# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

import os
import re
from functools import partial, reduce
from operator import and_
from subprocess import CalledProcessError
from typing import List, Optional, Set, Tuple

from ._git import CheckoutFailed, MergeBaseFailed, PullFailed
from ._metadata import APP


class _DmbException(Exception):
    pass


class _GitRepositoryWithoutBranches(_DmbException):
    """
    Exception for the time between "git init" and the first "git commit"
    where "git branch" will tell us that there are no branches
    """

    def __init__(self):
        super().__init__('This Git repository does not have any branches.')


class _NoSuchBranchException(_DmbException):

    def __init__(self, branch_name):
        super().__init__(f'There is no branch {branch_name!r}.')


class _NoSuchRemoteException(_DmbException):

    def __init__(self, remote_name):
        super().__init__(f'There is no remote {remote_name!r}.')


class _TooFewOptionsAvailable(_DmbException):
    pass


class _ZeroMergeTargetsException(_DmbException):

    def __init__(self):
        super().__init__('One or more existing target branch is required.')


class _InvalidRegexPattern(_DmbException):

    def __init__(self, pattern):
        super().__init__(f'Pattern "{pattern}" is not well-formed regular expression syntax '
                         '(with regard to Python module "re").')


class DeleteMergedBranches:
    _CONFIG_KEY_CONFIGURED = 'delete-merged-branches.configured'
    _CONFIG_VALUE_CONFIGURED = '5.0.0+'  # i.e. most ancient version with compatible config
    _CONFIG_VALUE_TRUE = 'true'
    _PATTERN_REMOTE_ENABLED = '^remote\\.(?P<name>[^ ]+)\\.dmb-enabled$'
    _PATTERN_BRANCH_EXCLUDED = '^branch\\.(?P<name>[^ ]+)\\.dmb-excluded$'
    _PATTERN_BRANCH_REQUIRED = '^branch\\.(?P<name>[^ ]+)\\.dmb-required$'
    _FORMAT_REMOTE_ENABLED = 'remote.{name}.dmb-enabled'
    _FORMAT_BRANCH_EXCLUDED = 'branch.{name}.dmb-excluded'
    _FORMAT_BRANCH_REQUIRED = 'branch.{name}.dmb-required'

    def __init__(self, git, messenger, confirmation, selector, effort_level):
        self._confirmation = confirmation
        self._messenger = messenger
        self._git = git
        self._selector = selector
        self._effort_using_git_cherry = effort_level >= 2
        self._effort_using_squashed_copies = effort_level >= 3

    def _interactively_edit_list(self, description, valid_names, old_names, format,
                                 min_selection_count) -> Set[str]:
        if len(valid_names) < min_selection_count:
            raise _TooFewOptionsAvailable

        help = ('(Press [Space] to toggle selection, [Enter]/[Return] to accept'
                ', [Ctrl]+[C] to quit.)')

        old_names = set(old_names)
        initial_selection = [i for i, name in enumerate(valid_names) if name in old_names]
        if valid_names:
            new_names = set(
                self._selector(self._messenger, valid_names, initial_selection, description, help,
                               min_selection_count))
        else:
            new_names = set()
        assert len(new_names) >= min_selection_count
        names_to_remove = old_names - new_names
        names_to_add = new_names - old_names

        for names, new_value in ((names_to_remove, None), (names_to_add, self._CONFIG_VALUE_TRUE)):
            for name in names:
                key = format.format(name=name)
                self._git.set_config(key, new_value)

        return new_names

    def _configure_required_branches(self, git_config) -> Set[str]:
        try:
            return self._interactively_edit_list(
                '[1/3] For a branch to be considered'
                ' fully merged, which other branches'
                ' must it have been merged to?',
                self._git.find_local_branches(),
                self.find_required_branches(git_config),
                self._FORMAT_BRANCH_REQUIRED,
                min_selection_count=1)
        except _TooFewOptionsAvailable:
            raise _GitRepositoryWithoutBranches

    def _configure_excluded_branches(self, git_config, new_required_branches: Set[str]):
        valid_names = sorted(set(self._git.find_all_branch_names()) - new_required_branches)
        self._interactively_edit_list(
            '[2/3] Which of these branches (if any)'
            ' should be kept around at all times?',
            valid_names,
            self.find_excluded_branches(git_config),
            self._FORMAT_BRANCH_EXCLUDED,
            min_selection_count=0)

    def _configure_enabled_remotes(self, git_config):
        self._interactively_edit_list(
            '[3/3] Which remotes (if any) do you want to enable'
            ' deletion of merged branches for?',
            self._git.find_remotes(),
            self.find_enabled_remotes(git_config),
            self._FORMAT_REMOTE_ENABLED,
            min_selection_count=0)

    def _configure(self, git_config):
        repo_basename = os.path.basename(os.getcwd())
        self._messenger.tell_info(f'Configure {APP} for repository {repo_basename!r}:')

        new_required_branches = self._configure_required_branches(git_config)
        self._configure_excluded_branches(git_config, new_required_branches)
        self._configure_enabled_remotes(git_config)
        self._git.set_config(self._CONFIG_KEY_CONFIGURED, self._CONFIG_VALUE_CONFIGURED)

    @classmethod
    def _is_configured(cls, git_config):
        return git_config.get(cls._CONFIG_KEY_CONFIGURED) == cls._CONFIG_VALUE_CONFIGURED

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
    def find_excluded_branches(cls, git_config):
        return cls._filter_git_config(git_config, cls._PATTERN_BRANCH_EXCLUDED)

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
            find_branches_that_were_merged_into = partial(self._git.find_merged_remote_branches_for,
                                                          remote_name)

        if len(required_target_branches) == 1:
            target_branch = next(iter(required_target_branches))
            branches_merged_to_all_required_targets = set(
                find_branches_that_were_merged_into(target_branch))
        else:
            branches_merged_to_all_required_targets = reduce(
                and_, (set(find_branches_that_were_merged_into(target_branch))
                       for target_branch in required_target_branches))

        return branches_merged_to_all_required_targets

    def _has_been_squash_merged_into(self, target_branch, topic_branch) -> bool:
        """
        Tries to detect a squashed merge, i.e. where a single commit
        on the target branch pulls in the sum of all commits
        between the common merge base commit and the tip of the topic branch.

        The implementation creates a temporary squashed copy of those commits
        and then asks ``git cherry`` if that squashed commit has an equivalent
        on the target branch.
        """
        try:
            merge_base_commit_sha1 = self._git.merge_base(target_branch, topic_branch)
        except MergeBaseFailed:
            return False
        squash_merge_commit_sha1 = self._git.commit_tree(message=f'Squash-merge {topic_branch!r}',
                                                         parent_committish=merge_base_commit_sha1,
                                                         tree=topic_branch + '^{tree}')

        cherry_lines = self._git.cherry(target_branch, squash_merge_commit_sha1)
        defacto_merged_into_target = all(line.startswith('-') for line in cherry_lines)
        return defacto_merged_into_target

    def _find_branches_merged_using_git_cherry(self, required_target_branches,
                                               candidate_branches) -> Set[str]:
        assert required_target_branches

        if not candidate_branches:
            return set()

        branches_merged_to_all_required_targets = set()
        candidates_for_squashed_merges = []

        for topic_branch in sorted(candidate_branches):
            assert topic_branch not in required_target_branches

            for target_branch in sorted(required_target_branches):
                cherry_lines = self._git.cherry(target_branch, topic_branch)
                defacto_merged_into_target = all(line.startswith('-') for line in cherry_lines)
                if not defacto_merged_into_target:
                    if len(cherry_lines) > 1:
                        candidates_for_squashed_merges.append(topic_branch)
                    break
            else:  # i.e. no break happened above
                branches_merged_to_all_required_targets.add(topic_branch)

        if self._effort_using_squashed_copies:
            check_for_squash_merges = True

            if candidates_for_squashed_merges:
                if self._git.has_detached_heads():
                    self._messenger.tell_info('Skipped further inspection of branches'
                                              ' because of detached HEAD.')
                    check_for_squash_merges = False

                if check_for_squash_merges:
                    if self._git.has_uncommitted_changes():
                        self._messenger.tell_info('Skipped further inspection of branches'
                                                  ' due to uncommitted changes.')
                        check_for_squash_merges = False

            if check_for_squash_merges:
                for topic_branch in candidates_for_squashed_merges:
                    for target_branch in sorted(required_target_branches):
                        defacto_merged_into_target = self._has_been_squash_merged_into(
                            target_branch=target_branch, topic_branch=topic_branch)
                        if not defacto_merged_into_target:
                            break
                    else:  # i.e. no break happened above
                        branches_merged_to_all_required_targets.add(topic_branch)

        return branches_merged_to_all_required_targets

    def _find_branches_merged_to_all_targets_for_single_remote(
            self, required_target_branches, excluded_branches: Set[str],
            remote_name: Optional[str]) -> Tuple[Set[str], Set[str]]:
        if remote_name is not None:
            excluded_branches = {
                f'{remote_name}/{branch_name}'
                for branch_name in excluded_branches
            }

        truly_merged_branches = (self._find_branches_merged_using_git_branch_merged(
            required_target_branches, remote_name=remote_name)) - excluded_branches

        if self._effort_using_git_cherry:
            if remote_name is None:
                all_branches_at_remote = set(self._git.find_local_branches())
            else:
                all_branches_at_remote = set(self._git.find_remote_branches_at(remote_name))
            if remote_name is not None:
                required_target_branches = {
                    f'{remote_name}/{branch_name}'
                    for branch_name in required_target_branches
                }
            branches_to_inspect_using_git_cherry = (all_branches_at_remote
                                                    - required_target_branches - excluded_branches
                                                    - truly_merged_branches)
            defacto_merged_branches = self._find_branches_merged_using_git_cherry(
                required_target_branches, branches_to_inspect_using_git_cherry)
        else:
            defacto_merged_branches = set()

        return (truly_merged_branches, defacto_merged_branches)

    def _report_branches_as_deleted(self, branch_names: Set[str], remote_name: str = None):
        branch_type = 'local' if (remote_name is None) else 'remote'
        info_text = f'{len(branch_names)} {branch_type} branch(es) deleted.'
        self._messenger.tell_info(info_text)

    def _delete_local_merged_branches_for(self, required_target_branches, excluded_branches):
        for working_tree_branch in self._git.find_working_tree_branches():
            branch_would_be_analyzed = (working_tree_branch is not None
                                        and working_tree_branch not in required_target_branches
                                        and working_tree_branch not in excluded_branches)
            if branch_would_be_analyzed:
                excluded_branches = excluded_branches | {working_tree_branch}
                self._messenger.tell_info(f'Skipped branch {working_tree_branch!r} '
                                          'because it is currently checked out.')

        truly_merged, defacto_merged = (self._find_branches_merged_to_all_targets_for_single_remote(
            required_target_branches, excluded_branches, remote_name=None))

        local_branches_to_delete = truly_merged | defacto_merged

        if not local_branches_to_delete:
            self._messenger.tell_info('No local branches deleted.')
            return

        description = (f'You are about to delete {len(local_branches_to_delete)}'
                       ' local branch(es):\n'
                       + '\n'.join(f'  - {name}'
                                   for name in sorted(local_branches_to_delete)) + '\n\nDelete?')
        if not self._confirmation.confirmed(description):
            return

        # NOTE: With regard to reporting, the idea is to
        #       - report all deleted local branches at once when deletion was successful, and to
        #       - not silence partial success
        #         when the first delete call was successful and the second call was not.
        self._git.delete_local_branches(truly_merged)
        try:
            self._git.delete_local_branches(defacto_merged, force=True)
        except CalledProcessError:
            self._report_branches_as_deleted(truly_merged)
            raise
        else:
            self._report_branches_as_deleted(truly_merged | defacto_merged)

    def _delete_remote_merged_branches_for(self, required_target_branches, excluded_branches,
                                           remote_name, all_branch_refs: Set[str]):
        if not all((f'{remote_name}/{branch_name}' in all_branch_refs)
                   for branch_name in required_target_branches):
            self._messenger.tell_info(f'Skipped remote {remote_name!r} '
                                      'as it does not have all required branches.')
            return

        truly_merged, defacto_merged = self._find_branches_merged_to_all_targets_for_single_remote(
            required_target_branches, excluded_branches, remote_name=remote_name)
        remote_branches_to_delete = [
            b for b in (truly_merged | defacto_merged) if b.startswith(f'{remote_name}/')
        ]

        if not remote_branches_to_delete:
            self._messenger.tell_info('No remote branches deleted.')
            return

        description = (f'You are about to delete {len(remote_branches_to_delete)} '
                       'remote branch(es):\n'
                       + '\n'.join(f'  - {name}'
                                   for name in sorted(remote_branches_to_delete)) + '\n\nDelete?')
        if not self._confirmation.confirmed(description):
            return

        self._git.delete_remote_branches(remote_branches_to_delete, remote_name)
        self._report_branches_as_deleted(remote_branches_to_delete, remote_name)

    def refresh_remotes(self, enabled_remotes):
        sorted_remotes = sorted(set(enabled_remotes))
        if not sorted_remotes:
            return

        description = (f'Do you want to run "git remote update --prune"'
                       f' for {len(sorted_remotes)} remote(s):\n'
                       + '\n'.join(f'  - {name}' for name in sorted_remotes) + '\n\nUpdate?')
        if not self._confirmation.confirmed(description):
            return

        for remote_name in sorted_remotes:
            self._git.update_and_prune_remote(remote_name)

    def detect_stale_remotes(self, enabled_remotes, required_target_branches):
        sorted_remotes = sorted(set(enabled_remotes))
        if not sorted_remotes:
            return

        sorted_required_target_branches = sorted(set(required_target_branches))
        assert sorted_required_target_branches

        for remote_name in enabled_remotes:
            remote_branches = set(self._git.find_remote_branches_at(remote_name))
            not_fully_pushed_branches = [
                branch for branch in sorted_required_target_branches
                if f'{remote_name}/{branch}' in remote_branches and
                self._git.has_unpushed_commits_on(branch, with_regard_to=f'{remote_name}/{branch}')
            ]

            if not_fully_pushed_branches:
                self._messenger.tell_info((f'Remote {remote_name!r} is not up to date with'
                                           f' {len(not_fully_pushed_branches)} local'
                                           ' branch(es):\n')
                                          + '\n'.join(f'  - {branch}'
                                                      for branch in not_fully_pushed_branches)
                                          + ('\n\nThis will likely impair detection'
                                             f' of merged branches for remote {remote_name!r}.'
                                             '\nPlease consider getting it back in sync'
                                             ' by running\n')
                                          + '\n'.join(f'  $ git push {remote_name} {branch}'
                                                      for branch in not_fully_pushed_branches)
                                          + f'\n\nand then invoking {APP}, again.')

    def refresh_target_branches(self, required_target_branches):
        sorted_branches = sorted(set(required_target_branches))
        if not sorted_branches:
            return

        initial_branch = self._git.find_current_branch()
        if initial_branch is None or self._git.has_detached_heads():
            self._messenger.tell_info('Skipped refreshing branches because of detached HEAD.')
            return

        if self._git.has_uncommitted_changes():
            self._messenger.tell_info('Skipped refreshing branches due to uncommitted changes.')
            return

        description = (f'Do you want to run "git pull --ff-only"'
                       f' for {len(sorted_branches)} branch(es):\n'
                       + '\n'.join(f'  - {name}' for name in sorted_branches) + '\n\nPull?')
        if not self._confirmation.confirmed(description):
            return

        needs_a_switch_back = False
        try:
            for branch_name in sorted_branches:
                if branch_name != initial_branch:
                    try:
                        self._git.checkout(branch_name)
                    except CheckoutFailed:
                        self._messenger.tell_error(f'Refreshing local branch {branch_name!r}'
                                                   ' failed'
                                                   ' because the branch cannot be checkout out.')
                        continue
                    needs_a_switch_back = True

                try:
                    self._git.pull_ff_only()
                except PullFailed:
                    self._messenger.tell_error(f'Refreshing local branch {branch_name!r} failed'
                                               ' because the branch cannot be pulled'
                                               ' with fast forward.')
        finally:
            if needs_a_switch_back:
                self._git.checkout(initial_branch)

    def delete_merged_branches(self, required_target_branches, excluded_branches, enabled_remotes):
        self._delete_local_merged_branches_for(required_target_branches, excluded_branches)
        all_branch_refs = set(self._git.find_all_branch_refs())
        for remote_name in enabled_remotes:
            self._delete_remote_merged_branches_for(required_target_branches, excluded_branches,
                                                    remote_name, all_branch_refs)

    def determine_excluded_branches(self, git_config: dict, excluded_branches: List[str],
                                    included_branches_patterns: List[str]) -> Set[str]:
        existing_branches = set(self._git.find_all_branch_names())
        if excluded_branches:
            excluded_branches_set = set(excluded_branches)
            invalid_branches = excluded_branches_set - existing_branches
            if invalid_branches:
                raise _NoSuchBranchException(sorted(invalid_branches)[0])
        else:
            excluded_branches_set = set()

        excluded_branches_set |= (set(self.find_excluded_branches(git_config)) & existing_branches)

        # The inclusion patterns are meant to work in logical conjunction ("and") but an empty
        # list should not exclude any branches.  So we'll add any existing branch to the exclusion
        # set that fails to match any of the inclusion patterns:
        for included_branches_pattern in included_branches_patterns:
            try:
                matcher = re.compile(included_branches_pattern)
            except re.error:
                raise _InvalidRegexPattern(included_branches_pattern)

            for branch_name in existing_branches:
                if matcher.search(branch_name):
                    continue
                excluded_branches_set.add(branch_name)

        return excluded_branches_set

    def determine_required_target_branches(self, git_config: dict,
                                           required_target_branches: List[str]):
        existing_branches = set(self._git.find_local_branches())
        if required_target_branches:
            required_target_branches_set = set(required_target_branches)
            invalid_branches = required_target_branches_set - existing_branches
            if invalid_branches:
                raise _NoSuchBranchException(required_target_branches[0])
        else:
            required_target_branches_set = (set(self.find_required_branches(git_config))
                                            & existing_branches)

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
            return (set(self.find_enabled_remotes(git_config)) & existing_remotes)
