# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

import subprocess
from tempfile import NamedTemporaryFile, TemporaryDirectory
from textwrap import dedent
from unittest import TestCase

from .._engine import DeleteMergedBranches
from .._git import Git
from .._messenger import Messenger


def run_script(content, cwd):
    header = dedent("""\
        set -e
        set -x
        export HOME=  # make global git config have no effect

        git init
        git config user.name git-deleted-merged-branches
        git config user.email gdmb@localhost
    """)

    with NamedTemporaryFile() as f:
        for text in (header, content):
            f.write(text.encode('utf-8'))
        f.flush()
        subprocess.check_call(['bash', f.name], cwd=cwd)


def create_git(work_dir):
    messenger = Messenger(colorize=False)
    return Git(messenger=messenger, ask=True, pretend=False, verbose=True,
               work_dir=work_dir)


def create_dmb(git, effort_level):
    return DeleteMergedBranches(git, messenger=None, confirmation=None,
                                effort_level=effort_level)


class MergeDetectionTest(TestCase):

    def test_effort_1_truly_merged(self):
        setup_script = dedent("""
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
