# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

class Confirmation:
    _CONFIRM_GOOD = ('', 'y', 'Y')
    _CONFIRM_BAD = ('n', 'N')
    _CONFIRM_KNOWN = _CONFIRM_GOOD + _CONFIRM_BAD

    def __init__(self, ask):
        self._ask = ask

    def confirmed(self, question):
        if not self._ask:
            return True

        while True:
            reply = input(f'{question} [Y/n] ')
            if reply in self._CONFIRM_KNOWN:
                break
        return reply in self._CONFIRM_GOOD
