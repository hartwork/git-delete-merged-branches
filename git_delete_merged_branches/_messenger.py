# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

import sys

import colorama

from ._shell import escape_for_shell_display

_INFO_COLOR = colorama.Fore.WHITE + colorama.Style.BRIGHT
_ERROR_COLOR = colorama.Fore.RED + colorama.Style.BRIGHT
_COMMAND_COLOR = colorama.Fore.CYAN
_QUESTION_COLOR = colorama.Fore.GREEN + colorama.Style.BRIGHT
_RESET_COLOR = colorama.Style.RESET_ALL


class Messenger:

    def __init__(self, colorize):
        self._colorize = colorize

        # Multi-line block of text should by separated from consecutive output (if any)
        # by a blank line to give it some "air".  This flag is a tiny state machine.
        self._air_needed = False

    def produce_air(self):
        if self._air_needed:
            print()
            self._air_needed = False

    def request_air(self, future_message):
        if '\n' in future_message:
            self._air_needed = True

    def _produce_and_request_air(self, future_message):
        self.produce_air()
        self.request_air(future_message)

    def tell_info(self, message):
        self._produce_and_request_air(message)
        if self._colorize:
            message = f'{_INFO_COLOR}{message}{_RESET_COLOR}'
        print(message)

    def tell_command(self, argv, comment):
        self._produce_and_request_air('')
        epilog = f'  # {comment}' if comment else ''
        argv = [escape_for_shell_display(arg) for arg in argv]
        message = f'# {" ".join(argv)}'
        if self._colorize:
            message = f'{_COMMAND_COLOR}{message}{_RESET_COLOR}'
        message += epilog

        print(message, file=sys.stderr)

    def tell_error(self, message):
        self._produce_and_request_air(message)
        message = f'Error: {message}'
        if self._colorize:
            message = f'{_ERROR_COLOR}{message}{_RESET_COLOR}'
        print(message, file=sys.stderr)

    def format_question(self, message):
        if self._colorize:
            message = f'{_QUESTION_COLOR}{message}{_RESET_COLOR}'
        return message
