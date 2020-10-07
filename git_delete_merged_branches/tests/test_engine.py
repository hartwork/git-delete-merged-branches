# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

import os
from tempfile import TemporaryDirectory
from textwrap import dedent
from unittest import TestCase

from parameterized import parameterized

from .._engine import DeleteMergedBranches
from .helpers import create_dmb, create_git, run_script


class MergeDetectionTest(TestCase):

    def test_effort_1_truly_merged(self):
        setup_script = dedent("""
            git init

            # Create a commit to base future branches upon
            echo line1 > file.txt
            git add file.txt
            git commit -m 'Add file.txt with one line'

            # Create a merged branch: With HEAD sitting in master's past
            git branch merged1

            # Create a merged branch: Topic branch with original commit
            git checkout -b merged2
            echo line2 >> file.txt
            git commit -a -m 'Add line 2'
            git checkout master
            git merge --no-ff --no-edit merged2

            # Create a not-merged branch
            git checkout -b not-merged1
            echo line3 >> file.txt
            git commit -a -m 'Add line 3'
        """)
        with TemporaryDirectory() as d:
            run_script(setup_script, cwd=d)
            git = create_git(d)
            dmb = create_dmb(git, effort_level=1)
            self.assertEqual(git.find_local_branches(),
                             ['master', 'merged1', 'merged2', 'not-merged1'])

            truly_merged, defacto_merged = (
                dmb._find_branches_merged_to_all_targets_for_single_remote(
                    {'master'}, set(), remote_name=None))

            self.assertEqual(truly_merged, {'merged1', 'merged2'})
            self.assertEqual(defacto_merged, set())

    def test_effort_2_unsquashed_cherries(self):
        setup_script = dedent("""
            git init

            # Create a commit to base future branches upon
            echo line1 > file1.txt
            git add file1.txt
            git commit -m 'Add file1.txt'

            # Create a de-facto merged branch: forward order
            git checkout -b defacto-merged1
            cp file1.txt file2.txt
            git add file2.txt
            git commit -m 'Add file2.txt'
            cp file1.txt file3.txt
            git add file3.txt
            git commit -m 'Add file3.txt'

            # Create a de-facto merged branch: backward order
            git checkout -b defacto-merged2 master
            cp file1.txt file3.txt
            git add file3.txt
            git commit -m 'Add file3.txt'
            cp file1.txt file2.txt
            git add file2.txt
            git commit -m 'Add file2.txt'

            # Add an extra commit on master so that we don't get
            # identical SHA1s when cherry-picking, after
            git checkout master
            cp file1.txt file4.txt
            git add file4.txt
            git commit -m 'Add file4.txt'

            # Get the commits on master that will make
            # branches defacto-merged{1,2} be detected as de-facto merged
            git cherry-pick defacto-merged1{^,}

            # Create a not-defacto-merged branch
            git checkout -b not-defacto-merged1 defacto-merged1
            cp file1.txt file5.txt
            git add file5.txt
            git commit -m 'Add file5.txt'
        """)
        with TemporaryDirectory() as d:
            run_script(setup_script, cwd=d)
            git = create_git(d)
            dmb = create_dmb(git, effort_level=2)
            self.assertEqual(git.find_local_branches(),
                             ['defacto-merged1', 'defacto-merged2', 'master',
                              'not-defacto-merged1'])

            truly_merged, defacto_merged = (
                dmb._find_branches_merged_to_all_targets_for_single_remote(
                    {'master'}, set(), remote_name=None))

            self.assertEqual(truly_merged, set())
            self.assertEqual(defacto_merged, {'defacto-merged1', 'defacto-merged2'})

    def test_effort_3_squashed_cherries(self):
        setup_script = dedent("""
            git init

            # Create a commit to base future branches upon
            echo line1 > file1.txt
            git add file1.txt
            git commit -m 'Add file1.txt'

            # Create a de-facto squash-merged branch: Adding up to full diff
            git checkout -b defacto-squash-merged1
            cp file1.txt file2.txt
            git add file2.txt
            git commit -m 'Add file2.txt'
            cp file1.txt file3.txt
            git add file3.txt
            git commit -m 'Add file3.txt'

            # Create de-facto squash-merged branch: With reverts, adding up
            git checkout -b defacto-squash-merged2
            git revert --no-edit HEAD
            git revert --no-edit HEAD  # i.e. revert the revert

            # Get the a squashed commit on master that will make
            # branches defacto-squash-merged{1,2} be detected as de-facto merged
            git checkout master
            git merge --squash defacto-squash-merged1
            git commit -m "Add squashed copy of 'defacto-squash-merged1'"

            # Create not-defacto-squash-merged branch: Squashed copy commit
            #                                          .. will not have a counterpart
            git checkout -b not-defacto-squash-merged1
            git revert --no-edit HEAD
        """)
        with TemporaryDirectory() as d:
            run_script(setup_script, cwd=d)
            git = create_git(d)
            dmb = create_dmb(git, effort_level=3)
            self.assertEqual(git.find_local_branches(),
                             ['defacto-squash-merged1', 'defacto-squash-merged2',
                              'master', 'not-defacto-squash-merged1'])

            truly_merged, defacto_merged = (
                dmb._find_branches_merged_to_all_targets_for_single_remote(
                    {'master'}, set(), remote_name=None))

            self.assertEqual(truly_merged, set())
            self.assertEqual(defacto_merged, {'defacto-squash-merged1',
                                              'defacto-squash-merged2'})


class RefreshTargetBranchesTest(TestCase):
    def test_refresh_gets_branches_back_in_sync(self):
        setup_script = dedent("""
            mkdir upstream
            cd upstream
                git init
                git commit --allow-empty -m 'Dummy commit #1'
                git branch pull-works
                git branch pull-trouble
                git checkout -b checkout-trouble
                    echo line1 > collision.txt
                    git add collision.txt
                    git commit -m 'Add collision.txt'
                git checkout master
            cd ..
            git clone -o upstream upstream downstream
            cd downstream
                git branch --track checkout-trouble upstream/checkout-trouble
                git branch --track pull-trouble upstream/pull-trouble
                git branch --track pull-works upstream/pull-works
            cd ..
            cd upstream
                git checkout pull-trouble
                    git merge --ff checkout-trouble
                git checkout pull-works
                    git commit --allow-empty -m 'Dummy commit #2'
            cd ..
            cd downstream
                git checkout -b topic1
                echo line1 > collision.txt  # uncommitted, just present
        """)

        with TemporaryDirectory() as d:
            run_script(setup_script, cwd=d)

            downstream_git = create_git(os.path.join(d, 'downstream'))
            downstream_dmb = create_dmb(downstream_git, effort_level=3)
            self.assertEqual(downstream_git.find_current_branch(), 'topic1')
            self.assertEqual(downstream_git.find_local_branches(), [
                'checkout-trouble', 'master', 'pull-trouble', 'pull-works', 'topic1'])
            downstream_dmb.refresh_remotes(['upstream'])
            self.assertEqual(len(downstream_git.cherry('pull-works', 'upstream/pull-works')), 1)

            downstream_dmb.refresh_target_branches(['checkout-trouble',
                                                    'pull-trouble',
                                                    'pull-works'])

            self.assertEqual(len(downstream_git.cherry('pull-works', 'upstream/pull-works')), 0)
            self.assertEqual(downstream_git.find_current_branch(), 'topic1')


class GitConfigKeysContainDotsTest(TestCase):
    @parameterized.expand([
        (DeleteMergedBranches.find_required_branches,
         'branch.release-1.0.x.dmb-required', 'release-1.0.x'),
        (DeleteMergedBranches.find_excluded_branches,
         'branch.release-1.0.x.dmb-excluded', 'release-1.0.x'),
        (DeleteMergedBranches.find_enabled_remotes,
         'remote.linux-6.x.dmb-enabled', 'linux-6.x'),
    ])
    def test_supports_branch_names_containing_dots(self, extractor_function, git_config_dict_key,
                                                   expected_value):
        assert '.' in expected_value
        git_config_dict = {
            git_config_dict_key: 'true',
        }
        self.assertEqual(extractor_function(git_config_dict), [expected_value])
