# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

from typing import List
from unittest.mock import Mock, patch

from clintermission import (CliMenuCursor, CliMenuStyle, CliMultiMenu,
                            CliSelectionStyle)
from prompt_toolkit import Application

from ._override import override


def _create_application_with_exit_guard(exit_allowed_func):
    """
    Derives a new class from prompt_toolkit.Application
    that asks ``exit_allowed_func`` for permission before exiting.
    """
    class ApplicationWithExitCheck(Application):
        @override
        def exit(self, *args, **kvargs) -> None:
            if not exit_allowed_func():
                return
            super().exit(*args, **kvargs)

    return ApplicationWithExitCheck


class _CliMenuNonHeader:
    """Fork of CliMenuHeader for non-header text"""
    def __init__(self, text, indent=False):
        self.text = text
        self.indent = indent
        self.focusable = False


class _ExtendedCliMultiMenu(CliMultiMenu):

    def __init__(self, initial_option_index=None, min_selection_count=0, non_header_style=None,
                 **kwargs):
        self.__initial_option_index = initial_option_index
        self.__cursor_initialized = False
        self.__min_selection_count = min_selection_count
        self.__non_header_style = non_header_style
        super().__init__(**kwargs)

    def _option_index_to_pos(self, option_index: int) -> int:
        """
        Finds the zero-based line number of the option with zero-based index ``option_index``.
        """
        for i, item in enumerate(self._items):
            if item.focusable:  # i.e. it is a selectable option
                if option_index == 0:
                    return i
                option_index -= 1
        else:
            raise ValueError('Not that many options')

    @override
    def sync_cursor_to_line(self, line, **kwargs):
        """
        Fork of CliMultiMenu.sync_cursor_to_line that hijacks the first call
        on this instance to set the intial cursor position
        """
        if not self.__cursor_initialized:
            if self.__initial_option_index is not None:
                line = self._option_index_to_pos(self.__initial_option_index)
            self.__cursor_initialized = True
        super().sync_cursor_to_line(line, **kwargs)

    def _is_exit_allowed(self) -> bool:
        if not self._success:
            return True
        if len(self._multi_selected) >= self.__min_selection_count:
            return True

        self._success = False  # revert affect of key-binding closure "accept"
        return False

    def add_non_header_text(self, text):
        """
        Fork of CliMenu.add_text that uses ``_CliMenuNonHeader ``rather than ``CliMenuHeader``
        """
        for line in text.split('\n'):
            self._items.append(_CliMenuNonHeader(line, indent=False))

    @override
    def _transform_line(self, ti):
        """
        Fork of CliMultiMenu._transform_line that patches in a different
        """
        item = self._items[ti.lineno]
        if not isinstance(item, _CliMenuNonHeader) or self.__non_header_style is None:
            return super()._transform_line(ti)

        with patch.object(self, '_style', Mock(header_style=self.__non_header_style)):
            return super()._transform_line(ti)

    @property
    def success(self):
        """
        Fork of CliMultiMenu.success that denies exiting while
        ``self._min_selection_count_satisfied`` is not satisfied.
        """
        application_class = _create_application_with_exit_guard(self._is_exit_allowed)
        with patch('clintermission.climenu.Application', application_class):
            return super().success


def multiselect(messenger, options, initial_selection, title, help,
                min_selection_count) -> List[str]:
    assert len(options) >= min_selection_count

    initial_option_index = initial_selection[0] if initial_selection else None

    menu = _ExtendedCliMultiMenu(
        initial_option_index=initial_option_index,
        min_selection_count=min_selection_count,
        non_header_style='',

        # From here on all standard CliMultiMenu:
        unselected_icon=CliSelectionStyle.SQUARE_BRACKETS[1],
        selected_icon=CliSelectionStyle.SQUARE_BRACKETS[0],
        style=CliMenuStyle(header_style='bold fg:ansibrightgreen',
                           highlight_style='bold fg:black bg:white'),
        indent=0,
        cursor=CliMenuCursor.TRIANGLE,
    )

    menu.add_header(title, indent=False)
    menu.add_non_header_text('')
    option_display_width = max(len(o) for o in options) + 2
    for i, option in enumerate(options):
        option_display = option.ljust(option_display_width)
        menu.add_option(option_display, item=option, selected=i in initial_selection)
    menu.add_non_header_text('')
    menu.add_non_header_text(help)

    messenger.produce_air()

    selected_options = menu.get_selection_item()
    if selected_options is None:
        raise KeyboardInterrupt

    messenger.request_air('\n')

    return selected_options
