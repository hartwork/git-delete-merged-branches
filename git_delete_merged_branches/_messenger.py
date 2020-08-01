# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

import colorama

_INFO_COLOR = colorama.Fore.WHITE + colorama.Style.BRIGHT
_RESET_COLOR = colorama.Style.RESET_ALL


class Messenger:
    def __init__(self, colorize):
        self._colorize = colorize

    def tell_info(self, message):
        if self._colorize:
            message = f'{_INFO_COLOR}{message}{_RESET_COLOR}'
        print(message)
