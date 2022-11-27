# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

import subprocess
from tempfile import NamedTemporaryFile
from textwrap import dedent
from unittest.mock import Mock

from .._confirm import Confirmation
from .._engine import DeleteMergedBranches
from .._git import Git
from .._messenger import Messenger


def run_script(content, cwd):
    header = dedent("""\
        set -e
        set -x
        export HOME=  # make global git config have no effect

        export GIT_AUTHOR_EMAIL=author1@localhost
        export GIT_AUTHOR_NAME='Author One'
        export GIT_COMMITTER_EMAIL=committer2@localhost
        export GIT_COMMITTER_NAME='Committer Two'
    """)

    with NamedTemporaryFile() as f:
        for text in (header, content):
            f.write(text.encode('utf-8'))
        f.flush()
        subprocess.check_call(['bash', f.name], cwd=cwd)


def create_git(work_dir: str) -> Git:
    messenger = Messenger(colorize=False)
    return Git(messenger=messenger, pretend=False, verbose=True, work_dir=work_dir)


def create_dmb(git: Git, effort_level: int) -> DeleteMergedBranches:
    messenger = Messenger(colorize=False)
    confirmation = Confirmation(messenger=messenger, ask=False)
    return DeleteMergedBranches(git,
                                messenger=messenger,
                                confirmation=confirmation,
                                selector=Mock(),
                                effort_level=effort_level)
