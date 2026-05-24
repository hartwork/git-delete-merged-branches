# Copyright (C) 2026 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

import copy
from typing import Any


def without(needle: list[Any], container: list[Any]) -> list[Any]:
    """
    Create a copy of a list with all occurences of sublist ``needle`` removed.
    """
    if not needle:
        return copy.copy(container)

    needle_first = needle[0]
    needle_len = len(needle)

    start_at = 0
    result = []

    while True:
        # Find the potential start of a match
        try:
            found_at = container.index(needle_first, start_at)
        except ValueError:  # i.e. not found
            # Copy the full remainder, and stop
            result.extend(container[start_at:])
            break

        # Do we have an actual match?
        if container[found_at : found_at + needle_len] == needle:
            # Yes: skip the match, continue
            result.extend(container[start_at:found_at])
            start_at = found_at + needle_len
        else:
            # No: continue with next character
            result.extend(container[start_at : found_at + 1])
            start_at = found_at + 1

    return result
