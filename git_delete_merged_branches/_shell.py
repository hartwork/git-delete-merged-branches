# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

_NEED_ESCAPING_INSIDE_DOUBLE_QUOTES = set('!`"$\\')
_NEED_ESCAPING_WITHOUT_QUOTES = _NEED_ESCAPING_INSIDE_DOUBLE_QUOTES | set('\' {}()?*&<>;#')


def _escape_for_double_quotes(text: str) -> str:
    escape = {c: f'\\{c}' for c in _NEED_ESCAPING_INSIDE_DOUBLE_QUOTES}
    escaped = ''.join(escape.get(c, c) for c in text)
    return escaped


def escape_for_shell_display(text: str) -> str:
    """
    Format text for display as part of a shell command
    close to what a human would write and expect to read.

    In detail, the requirements are:
    1. Do not escape spaces but rather surround by quotes,
       single or double.
    2. Do not surround by any quotes if the string does not
       contain spaces and is not the empty string.
    3. Prefer single quotes over double quotes, i.e. use double
       quotes only when single quotes are already present.
    """
    if not text:
        return "''"

    if ' ' in text:
        # Is surrounding by single quotes an option?
        if "'" in text:
            # Surrounding by single quotes is not an option;
            # so escape for use inside double quotes
            return f'"{_escape_for_double_quotes(text)}"'
        else:
            return f"'{text}'"

    needs_escaping = any((c in _NEED_ESCAPING_WITHOUT_QUOTES) for c in text)
    if not needs_escaping:
        return text

    # Is surrounding by single quotes an option?
    if "'" in text:
        return f'"{_escape_for_double_quotes(text)}"'
    else:
        return f"'{text}'"
