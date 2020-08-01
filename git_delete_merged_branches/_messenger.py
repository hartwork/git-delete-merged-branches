# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

import sys

import colorama

_INFO_COLOR = colorama.Fore.WHITE + colorama.Style.BRIGHT
_ERROR_COLOR = colorama.Fore.RED + colorama.Style.BRIGHT
_COMMAND_COLOR = colorama.Fore.CYAN
_QUESTION_COLOR = colorama.Fore.GREEN + colorama.Style.BRIGHT
_RESET_COLOR = colorama.Style.RESET_ALL


class Messenger:
    def __init__(self, colorize):
        self._colorize = colorize

    def tell_info(self, message):
        if self._colorize:
            message = f'{_INFO_COLOR}{message}{_RESET_COLOR}'
        print(message)

    def tell_command(self, argv, comment):
        epilog = f'  # {comment}' if comment else ''
        message = f'# {" ".join(argv)}'
        if self._colorize:
            message = f'{_COMMAND_COLOR}{message}{_RESET_COLOR}'
        message += epilog

        print(message, file=sys.stderr)

    def tell_error(self, message):
        message = f'Error: {message}'
        if self._colorize:
            message = f'{_ERROR_COLOR}{message}{_RESET_COLOR}'
        print(message, file=sys.stderr)

    def format_question(self, message):
        if self._colorize:
            message = f'{_QUESTION_COLOR}{message}{_RESET_COLOR}'
        return message
