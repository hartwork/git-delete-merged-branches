# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

import re

import colorama

_SECTION_COLOR = colorama.Fore.WHITE + colorama.Style.BRIGHT
_ARGUMENT_COLOR = colorama.Fore.GREEN + colorama.Style.BRIGHT
_PARAMETER_COLOR = colorama.Fore.GREEN
_PROG_COLOR = colorama.Fore.CYAN + colorama.Style.BRIGHT
_URL_COLOR = colorama.Fore.MAGENTA + colorama.Style.BRIGHT
_RESET_COLOR = colorama.Style.RESET_ALL

_SUBSTITUTIONS = (
    ('^(.+):$', f'{_SECTION_COLOR}\\1{_RESET_COLOR}:'),
    ('(?<!\\w)(--?[a-z-]+) ([A-Z_]+)',
     f'{_ARGUMENT_COLOR}\\1{_RESET_COLOR} {_PARAMETER_COLOR}\\2{_RESET_COLOR}'),
    ('(?<!\\w)((?!--?merged)--?[a-z-]+)', f'{_ARGUMENT_COLOR}\\1{_RESET_COLOR}'),
    ('^(usage): ([^ ]+)\\b',
     f'{_SECTION_COLOR}\\1{_RESET_COLOR}: {_PROG_COLOR}\\2{_RESET_COLOR}'),
    ('(https://[^ ]+[^ .])', f'{_URL_COLOR}\\1{_RESET_COLOR}'),
)


def add_color_to_formatter_class(formatter_class):
    class_name = formatter_class.__name__.replace('Formatter', 'ColorFormatter')

    class Class(formatter_class):
        def format_help(self):
            text = super().format_help()
            for pattern, replacement in _SUBSTITUTIONS:
                matcher = re.compile(pattern, flags=re.MULTILINE)
                text = matcher.sub(replacement, text)
            return text

    Class.__name__ = class_name

    return Class
