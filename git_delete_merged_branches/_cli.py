# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

import argparse
import os
import sys
import traceback
from argparse import RawDescriptionHelpFormatter
from signal import SIGINT
from subprocess import CalledProcessError
from textwrap import dedent

import colorama

from ._argparse_color import add_color_to_formatter_class
from ._confirm import Confirmation
from ._engine import DeleteMergedBranches
from ._git import Git
from ._messenger import Messenger
from ._metadata import APP, DESCRIPTION, VERSION


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

    parser = argparse.ArgumentParser(prog=APP, add_help=False,
                                     description=DESCRIPTION, epilog=_EPILOG,
                                     formatter_class=formatter_class)

    modes = parser.add_argument_group('modes').add_mutually_exclusive_group()
    modes.add_argument('--configure', dest='force_reconfiguration', action='store_true',
                       help=f'configure {APP} and exit (without processing any branches)')
    modes.add_argument('--help', '-h', action='help', help='show this help message and exit')
    modes.add_argument('--version', action='version', version='%(prog)s ' + VERSION)

    rules = parser.add_argument_group('rules')
    rules.add_argument('--branch', '-b', metavar='BRANCH', dest='required_target_branches',
                       default=[], action='append',
                       help='require the given branch as a merge target (instead of what is'
                            ' configured for this repository); can be passed multiple times')
    rules.add_argument('--effort', metavar='LEVEL', dest='effort_level',
                       type=int, default=2, choices=[1, 2, 3],
                       help='level of effort to put into finding merged branches'
                            '; level 1 uses nothing but "git branch --merged"'
                            ', level 2 adds use of "git cherry"'
                            ', level 3 adds use of "git cherry" on temporary squashed copies'
                            ' (default level: %(default)d)')

    scope = parser.add_argument_group('scope')
    scope.add_argument('--remote', '-r', metavar='REMOTE', dest='enabled_remotes', default=[],
                       action='append',
                       help='process the given remote (instead of the remotes that are'
                            ' configured for this repository); can be passed multiple times')
    scope.add_argument('--exclude', '-x', metavar='BRANCH', dest='excluded_branches',
                       default=[], action='append',
                       help='exclude the given branch from deletion'
                            ' (instead of what is configured for this repository)'
                            '; can be passed multiple times')

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
    git = Git(messenger, pretend=config.pretend, verbose=config.verbose)
    confirmation = Confirmation(messenger, ask=config.ask)
    dmb = DeleteMergedBranches(git, messenger, confirmation, config.effort_level)

    git_config = dmb.ensure_configured(config.force_reconfiguration)
    if config.force_reconfiguration:
        return

    required_target_branches = dmb.determine_required_target_branches(
        git_config, config.required_target_branches)
    excluded_branches = dmb.determine_excluded_branches(git_config,
                                                        config.excluded_branches)
    enabled_remotes = dmb.determine_enabled_remotes(git_config, config.enabled_remotes)

    dmb.refresh_remotes(enabled_remotes)
    dmb.detect_stale_remotes(enabled_remotes, required_target_branches)
    dmb.refresh_target_branches(required_target_branches)
    dmb.delete_merged_branches(required_target_branches, excluded_branches, enabled_remotes)


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
