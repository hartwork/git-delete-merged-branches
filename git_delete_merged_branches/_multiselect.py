# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

from abc import ABC
from dataclasses import dataclass
from functools import partial
from typing import Any, Callable, List, Optional
from unittest.mock import patch

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import is_searching
from prompt_toolkit.formatted_text.base import StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.processors import (Processor, Transformation,
                                              TransformationInput)
from prompt_toolkit.search import SearchState
from prompt_toolkit.widgets import SearchToolbar

from ._messenger import Messenger


class _LineRenderProcessor(Processor):
    """
    A Prompt Toolkit input processor for Buffer that formats lines for display to the user.
    """

    def __init__(self, prompt: '_MultiSelectPrompt'):
        self._prompt = prompt

    def apply_transformation(self, transformation_input: TransformationInput
                             ) -> Transformation:
        line_info = self._prompt.lines[transformation_input.lineno]
        line_is_item = isinstance(line_info, self._prompt.ItemLine)

        new_fragments: StyleAndTextTuples = []

        if line_is_item:
            highlighted = transformation_input.lineno == self._prompt.get_cursor_line()
            cursor = '▶' if highlighted else ' '
            checkmark = 'x' if line_info.selected else ' '
            fallback_style = (self._prompt.highlighted_style
                              if highlighted else
                              self._prompt.neutral_style)
            new_fragments.append((fallback_style, f'{cursor} [{checkmark}] '))
        elif isinstance(line_info, self._prompt.HeaderLine):
            fallback_style = self._prompt.header_style
        else:
            fallback_style = self._prompt.neutral_style

        # Apply new style where adequate
        for fragment in transformation_input.fragments:
            old_style, text = fragment

            # NOTE: The idea is to respect search result markers (that have been inserted
            #       by HighlightSearchProcessor or HighlightIncrementalSearchProcessor)
            #       in item text, and only there.
            if line_is_item:
                new_style = old_style or fallback_style
            else:
                new_style = fallback_style

            new_fragments.append((new_style, text))

        # Add right padding
        if line_is_item:
            padding_width = 2 + (self._prompt.peak_item_label_length - len(line_info.text))
            new_fragments.append((fallback_style, ' ' * padding_width))

        return Transformation(fragments=new_fragments)


class _LineJumpingBuffer(Buffer):
    """
    A Prompt Toolkit Buffer that will skip all but the first search match per line
    when iterating search matches using keys "n" and "N".
    """

    def apply_search(
            self,
            search_state: SearchState,
            include_current_position: bool = True,
            count: int = 1,
    ) -> None:
        previous_cursor_position = self.cursor_position
        previous_line_index, _ = self.document.translate_index_to_position(self.cursor_position)

        while True:
            super().apply_search(search_state=search_state,
                                 include_current_position=include_current_position,
                                 count=count)
            if self.cursor_position == previous_cursor_position:
                # The call to search has not moved the cursor, search has ended
                return

            current_line_index, _ = self.document.translate_index_to_position(self.cursor_position)
            if current_line_index != previous_line_index:
                # We changed lines already, that's all we wanted
                return

            previous_cursor_position = self.cursor_position
            previous_line_index = current_line_index


class _MultiSelectPrompt:
    """
    An interactive multi-select using the terminal, based on Prompt Toolkit.
    """

    @dataclass
    class _LineBase(ABC):
        text: str

    @dataclass
    class PlainLine(_LineBase):
        pass

    @dataclass
    class HeaderLine(_LineBase):
        pass

    @dataclass
    class ItemLine(_LineBase):
        item_index: int
        line_index: int
        value: Any
        selected: bool

    def __init__(self, highlighted_style: str = '', header_style: str = '',
                 initial_cursor_index=0, min_selection_count=0):
        self.neutral_style: str = ''
        self.highlighted_style: str = highlighted_style
        self.header_style: str = header_style

        self._initial_cursor_item_index: int = initial_cursor_index
        self._min_selection_count: int = min_selection_count

        self._items: List[_MultiSelectPrompt._ItemBase] = []
        self.peak_item_label_length: int = 0
        self.lines: [_MultiSelectPrompt.ItemLine] = []

        self._buffer: Optional[Buffer] = None
        self._document: Optional[Document] = None
        self._accepted_selection: List[Any] = None

    def _move_cursor_one_page_vertically(self, upwards: bool):
        page_height_in_lines = 10
        current_line_index = self.get_cursor_line()

        if upwards:
            new_line_index = max(self._items[0].line_index,
                                 current_line_index - page_height_in_lines)
        else:
            new_line_index = min(self._items[-1].line_index,
                                 current_line_index + page_height_in_lines)

        self._move_cursor_to_line(new_line_index)

    def _move_cursor_to_line(self, line_index: int):
        self._buffer.cursor_position = \
            self._document.translate_row_col_to_index(row=line_index, col=0)

    def get_cursor_line(self):
        row, col = self._document.translate_index_to_position(self._buffer.cursor_position)
        return row

    def _move_cursor_one_step_vertically(self, upwards: bool):
        if len(self._items) < 2:
            return

        current_line_index = self.get_cursor_line()

        if upwards:
            if current_line_index == 0:
                return
            candidates = range(current_line_index - 1, 0, -1)
        else:
            if current_line_index == len(self.lines) - 1:
                return
            candidates = range(current_line_index + 1, len(self.lines) - 1, +1)

        for candidate_line_index in candidates:
            line_info = self.lines[candidate_line_index]
            if isinstance(line_info, self.ItemLine):
                self._move_cursor_to_line(candidate_line_index)
                break

    def _on_move_line_down(self, _event):
        self._move_cursor_one_step_vertically(upwards=False)

    def _on_move_line_up(self, _event):
        self._move_cursor_one_step_vertically(upwards=True)

    def _on_move_page_up(self, _event):
        self._move_cursor_one_page_vertically(upwards=True)

    def _on_move_page_down(self, _event):
        self._move_cursor_one_page_vertically(upwards=False)

    def _on_move_to_first(self, _event):
        self._move_cursor_to_line(self._items[0].line_index)

    def _on_move_to_last(self, _event):
        self._move_cursor_to_line(self._items[-1].line_index)

    def _on_toggle(self, _event):
        line_index = self.get_cursor_line()
        line_info = self.lines[line_index]
        line_info.selected = not line_info.selected

    def _on_accept(self, event):
        selected_values = self._collect_selected_values()
        if len(selected_values) < self._min_selection_count:
            return
        self._accepted_selection = selected_values
        event.app.exit()

    def _on_abort(self, event):
        event.app.exit()

    def add_header(self, text):
        self.lines.append(self.HeaderLine(text))

    def add_item(self, value: Any, label: str = None, selected: bool = False):
        if label is None:
            label = str(value)

        self.peak_item_label_length = max(self.peak_item_label_length, len(label))

        item_line = self.ItemLine(selected=selected, item_index=len(self._items),
                                  line_index=len(self.lines), text=label, value=value)

        self.lines.append(item_line)
        self._items.append(item_line)

    def add_text(self, text):
        self.lines.append(self.PlainLine(text))

    def _create_key_bindings(self):
        key_bindings = KeyBindings()

        key_bindings.add('c-c')(self._on_abort)
        key_bindings.add('q', filter=~is_searching)(self._on_abort)

        key_bindings.add('space', filter=~is_searching)(self._on_toggle)

        for key in ('enter', 'right'):
            key_bindings.add(key, filter=~is_searching)(self._on_accept)

        for key in ('up', 'k'):
            key_bindings.add(key, filter=~is_searching)(self._on_move_line_up)
        for key in ('down', 'j'):
            key_bindings.add(key, filter=~is_searching)(self._on_move_line_down)

        key_bindings.add('pageup', filter=~is_searching)(self._on_move_page_up)
        key_bindings.add('pagedown', filter=~is_searching)(self._on_move_page_down)
        key_bindings.add('home', filter=~is_searching)(self._on_move_to_first)
        key_bindings.add('end', filter=~is_searching)(self._on_move_to_last)

        return key_bindings

    def _create_layout(self):
        search = SearchToolbar(ignore_case=True)
        buffer_control = BufferControl(buffer=self._buffer,
                                       input_processors=[_LineRenderProcessor(prompt=self)],
                                       preview_search=True,
                                       search_buffer_control=search.control)
        hsplit = HSplit([Window(buffer_control,
                                always_hide_cursor=True,
                                wrap_lines=True), search])
        return Layout(hsplit)

    def _collect_selected_values(self):
        return [item.value for item in self._items if item.selected]

    def _create_document_class(self, prompt: '_MultiSelectPrompt') -> Document:
        class ItemOnlySearchDocument(Document):
            """A Document that suppresses search results from non-item lines"""
            def _skip_non_item_matches(self, func: Callable, count: int) -> Optional[int]:
                while True:
                    index = func(count=count)
                    if index is None:
                        return None

                    effective_index = index + self.cursor_position
                    row, _col = self.translate_index_to_position(effective_index)
                    if isinstance(prompt.lines[row], prompt.ItemLine):
                        return index

                    count += 1  # i.e. retry with next match

            # override
            def find(self,
                     sub: str,
                     in_current_line: bool = False,
                     include_current_position: bool = False,
                     ignore_case: bool = False,
                     count: int = 1) -> Optional[int]:
                func = partial(super().find,
                               sub=sub,
                               in_current_line=in_current_line,
                               include_current_position=include_current_position,
                               ignore_case=ignore_case)
                return self._skip_non_item_matches(func, count)

            # override
            def find_backwards(
                    self,
                    sub: str,
                    in_current_line: bool = False,
                    ignore_case: bool = False,
                    count: int = 1,
            ) -> Optional[int]:
                func = partial(super().find_backwards,
                               sub=sub,
                               in_current_line=in_current_line,
                               ignore_case=ignore_case)
                return self._skip_non_item_matches(func, count)

        return ItemOnlySearchDocument

    def get_selected_values(self) -> List[Any]:
        document_class = self._create_document_class(prompt=self)
        self._document = document_class(text='\n'.join(line.text for line in self.lines))

        # Prompt Toolkit's Buffer is calling "Document(..)" internally,
        # and this patch will make it use our CustomSearchDocument everywhere.
        with patch('prompt_toolkit.buffer.Document', document_class):
            self._buffer = _LineJumpingBuffer(read_only=True, document=self._document)
            app = Application(key_bindings=self._create_key_bindings(),
                              layout=self._create_layout())

            self._move_cursor_to_line(self._items[self._initial_cursor_item_index].line_index)
            app.run()

            return self._accepted_selection


def multiselect(messenger: Messenger, options: List[str], initial_selection: List[int],
                title: str, help: str, min_selection_count: int) -> List[str]:
    assert len(options) >= min_selection_count

    menu = _MultiSelectPrompt(
        highlighted_style='bold fg:black bg:white',
        header_style='bold fg:ansibrightgreen',
        initial_cursor_index=initial_selection[0] if initial_selection else 0,
        min_selection_count=min_selection_count,
    )

    menu.add_header(title)
    menu.add_text('')
    for i, option in enumerate(options):
        menu.add_item(option, selected=i in initial_selection)
    menu.add_text('')
    menu.add_text(help)

    messenger.produce_air()

    selected_options = menu.get_selected_values()
    if selected_options is None:
        raise KeyboardInterrupt

    messenger.request_air('\n')

    return selected_options
