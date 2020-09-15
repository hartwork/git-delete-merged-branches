# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

from typing import List

from clintermission import (CliMenuCursor, CliMenuStyle, CliMultiMenu,
                            CliSelectionStyle)


def multiselect(messenger, options, initial_selection, title, help,
                min_selection_count) -> List[str]:
    assert len(options) >= min_selection_count

    highlighted_style = 'bold fg:black bg:white'
    header_style = 'bold fg:ansibrightgreen'

    initial_option_index = initial_selection[0] if initial_selection else 0

    menu = CliMultiMenu(
        initial_pos=initial_option_index,
        min_selection_count=min_selection_count,
        style=CliMenuStyle(
            option='',
            highlighted=highlighted_style,
            text='',
            selected='',
            selected_highlighted=highlighted_style,
        ),
        indent=0,
        cursor=CliMenuCursor.TRIANGLE,
        option_prefix=' ',
        selection_icons=CliSelectionStyle.SQUARE_BRACKETS,
        option_suffix='  ',
        right_pad_options=True,
    )

    menu.add_header(title, indent=False, style=header_style)
    menu.add_text('', indent=False)
    for i, option in enumerate(options):
        menu.add_option(option, selected=i in initial_selection)
    menu.add_text('', indent=False)
    menu.add_text(help, indent=False)

    messenger.produce_air()

    selected_options = menu.get_selection_item()
    if selected_options is None:
        raise KeyboardInterrupt

    messenger.request_air('\n')

    return selected_options
