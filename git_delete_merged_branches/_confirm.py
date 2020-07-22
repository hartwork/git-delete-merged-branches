# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

import sys


class Confirmation:
    _CONFIRM_GOOD = ('', 'y', 'Y')
    _CONFIRM_BAD = ('n', 'N')
    _CONFIRM_KNOWN = _CONFIRM_GOOD + _CONFIRM_BAD
    _EXIT_CODE_ABORTED = 2

    def __init__(self, ask):
        self._ask = ask

    def _confirm(self, question):
        if not self._ask:
            return True

        while True:
            reply = input(f'{question} [Y/n] ')
            if reply in self._CONFIRM_KNOWN:
                break
        return reply in self._CONFIRM_GOOD

    def require_for(self, description):
        if not self._confirm(description):
            sys.exit(self._EXIT_CODE_ABORTED)
