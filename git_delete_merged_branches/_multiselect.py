# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

from abc import ABC
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from prompt_toolkit.application import Application
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document
from prompt_toolkit.filters import is_searching
from prompt_toolkit.formatted_text.base import StyleAndTextTuples
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.containers import Container, VerticalAlign
from prompt_toolkit.layout.controls import BufferControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout.mouse_handlers import MouseHandlers
from prompt_toolkit.layout.processors import Processor, Transformation, TransformationInput
from prompt_toolkit.layout.screen import Screen, WritePosition
from prompt_toolkit.layout.scrollable_pane import ScrollablePane, ScrollOffsets
from prompt_toolkit.search import SearchState
from prompt_toolkit.widgets import SearchToolbar

from ._messenger import Messenger


class _ItemRenderProcessor(Processor):
    """
    A Prompt Toolkit input processor for Buffer that formats lines for display to the user.
    """

    def __init__(self, prompt: '_MultiSelectPrompt'):
        self._prompt = prompt

    def apply_transformation(self, transformation_input: TransformationInput) -> Transformation:
        line_info = self._prompt.item_lines[transformation_input.lineno]

        new_fragments: StyleAndTextTuples = []

        highlighted = transformation_input.lineno == self._prompt.get_cursor_line()
        cursor = '▶' if highlighted else ' '
        checkmark = 'x' if line_info.selected else ' '
        fallback_style = (self._prompt.highlighted_style
                          if highlighted else self._prompt.neutral_style)
        new_fragments.append((fallback_style, f'{cursor} [{checkmark}] '))

        # Apply new style where adequate
        for fragment in transformation_input.fragments:
            old_style, text = fragment

            # NOTE: The idea is to respect search result markers (that have been inserted
            #       by HighlightSearchProcessor or HighlightIncrementalSearchProcessor)
            #       in item text, and only there.
            new_style = old_style or fallback_style
            new_fragments.append((new_style, text))

        # Add right padding
        padding_width = 2 + (self._prompt.peak_item_label_length - len(line_info.text))
        new_fragments.append((fallback_style, ' ' * padding_width))

        return Transformation(fragments=new_fragments)


class _NonItemRenderProcessor(Processor):
    """
    A Prompt Toolkit input processor for Buffer that formats lines for display to the user.
    """

    def __init__(self, prompt: '_MultiSelectPrompt', lines: List):
        self._prompt = prompt
        self._lines = lines

    def apply_transformation(self, transformation_input: TransformationInput) -> Transformation:
        line_info = self._lines[transformation_input.lineno]

        if isinstance(line_info, self._prompt.HeaderLine):
            new_style = self._prompt.header_style
        else:
            new_style = self._prompt.neutral_style

        new_fragments: StyleAndTextTuples = [(new_style, text)
                                             for _old_style, text in transformation_input.fragments]

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


class _HeightTrackingScrollablePane(ScrollablePane):
    """
    A copy of ``ScrollablePane`` that remembers the latest rendering height.
    """

    def __init__(self, content: Container, **kwargs):
        super().__init__(content=content, **kwargs)
        self.current_height = None

    def write_to_screen(
        self,
        screen: Screen,
        mouse_handlers: MouseHandlers,
        write_position: WritePosition,
        parent_style: str,
        erase_bg: bool,
        z_index: Optional[int],
    ) -> None:
        self.current_height = write_position.height
        super().write_to_screen(screen=screen,
                                mouse_handlers=mouse_handlers,
                                write_position=write_position,
                                parent_style=parent_style,
                                erase_bg=erase_bg,
                                z_index=z_index)


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
        value: Any
        selected: bool

    def __init__(self,
                 highlighted_style: str = '',
                 header_style: str = '',
                 initial_cursor_index=0,
                 min_selection_count=0):
        self.neutral_style: str = ''
        self.highlighted_style: str = highlighted_style
        self.header_style: str = header_style

        self._initial_cursor_item_index: int = initial_cursor_index
        self._min_selection_count: int = min_selection_count

        self.peak_item_label_length: int = 0
        self.item_lines: [_MultiSelectPrompt.ItemLine] = []
        self._header_lines: [_MultiSelectPrompt.HeaderLine] = []
        self._footer_lines: [_MultiSelectPrompt.PlainLine] = []

        self._item_selection_pane: Optional[_HeightTrackingScrollablePane] = None
        self._buffer: Optional[Buffer] = None
        self._document: Optional[Document] = None
        self._accepted_selection: List[Any] = None

    def _move_cursor_one_page_vertically(self, upwards: bool):
        render_cursor_line = (self._item_selection_pane.content.render_info.cursor_position.y
                              - self._item_selection_pane.vertical_scroll)
        page_height_in_lines = self._item_selection_pane.current_height

        if upwards and render_cursor_line > 0:
            new_line_index = self.get_cursor_line() - render_cursor_line
        elif not upwards and render_cursor_line < page_height_in_lines - 1:
            new_line_index = self.get_cursor_line() + (page_height_in_lines - render_cursor_line
                                                       - 1)
        else:
            current_line_index = self.get_cursor_line()
            if upwards:
                new_line_index = max(0, current_line_index - page_height_in_lines)
            else:
                new_line_index = min(
                    len(self.item_lines) - 1, current_line_index + page_height_in_lines)

        self._move_cursor_to_line(new_line_index)

    def _move_cursor_to_line(self, line_index: int):
        self._buffer.cursor_position = \
            self._document.translate_row_col_to_index(row=line_index, col=0)

    def get_cursor_line(self):
        row, col = self._document.translate_index_to_position(self._buffer.cursor_position)
        return row

    def _move_cursor_one_step_vertically(self, upwards: bool):
        if len(self.item_lines) < 2:
            return

        current_line_index = self.get_cursor_line()

        # Can we even move any further in that direction?
        if ((upwards and current_line_index == 0)
                or (not upwards and current_line_index == len(self.item_lines) - 1)):
            return

        self._move_cursor_to_line(current_line_index + (-1 if upwards else 1))

    def _on_move_line_down(self, _event):
        self._move_cursor_one_step_vertically(upwards=False)

    def _on_move_line_up(self, _event):
        self._move_cursor_one_step_vertically(upwards=True)

    def _on_move_page_up(self, _event):
        self._move_cursor_one_page_vertically(upwards=True)

    def _on_move_page_down(self, _event):
        self._move_cursor_one_page_vertically(upwards=False)

    def _on_move_to_first(self, _event):
        self._move_cursor_to_line(0)

    def _on_move_to_last(self, _event):
        self._move_cursor_to_line(len(self.item_lines) - 1)

    def _on_toggle(self, _event):
        line_index = self.get_cursor_line()
        line_info = self.item_lines[line_index]
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
        self._header_lines.append(self.HeaderLine(text))

    def add_item(self, value: Any, label: str = None, selected: bool = False):
        if label is None:
            label = str(value)

        self.peak_item_label_length = max(self.peak_item_label_length, len(label))

        item_line = self.ItemLine(selected=selected, text=label, value=value)

        self.item_lines.append(item_line)

    def add_footer(self, text):
        self._footer_lines.append(self.PlainLine(text))

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

    def _create_text_display_window_for(self, lines: List[_LineBase]) -> Window:
        document = Document(text='\n'.join(line.text for line in lines))
        buffer = Buffer(read_only=True, document=document)
        buffer_control = BufferControl(
            buffer=buffer, input_processors=[_NonItemRenderProcessor(prompt=self, lines=lines)])
        return Window(buffer_control,
                      wrap_lines=True,
                      height=Dimension(min=len(lines), max=len(lines)))

    def _create_layout(self) -> Tuple[Layout, _HeightTrackingScrollablePane]:
        header = self._create_text_display_window_for(self._header_lines)
        footer = self._create_text_display_window_for(self._footer_lines)

        search = SearchToolbar(ignore_case=True)
        buffer_control = BufferControl(buffer=self._buffer,
                                       input_processors=[_ItemRenderProcessor(prompt=self)],
                                       preview_search=True,
                                       search_buffer_control=search.control)
        item_selection_window = Window(buffer_control, always_hide_cursor=True, wrap_lines=True)

        pane_scroll_offsets = ScrollOffsets(top=0, bottom=0)
        pane_height = Dimension(min=1,
                                max=self._document.line_count,
                                preferred=self._document.line_count)
        item_selection_pane = _HeightTrackingScrollablePane(item_selection_window,
                                                            height=pane_height,
                                                            scroll_offsets=pane_scroll_offsets)
        item_selection_pane.show_scrollbar = lambda: (item_selection_pane.current_height or 0
                                                      ) < self._document.line_count

        item_selection_pane_plus_search = HSplit([item_selection_pane, search])
        hsplit = HSplit([header, item_selection_pane_plus_search, footer],
                        padding=1,
                        align=VerticalAlign.TOP)
        return Layout(hsplit, focused_element=item_selection_pane), item_selection_pane

    def _collect_selected_values(self):
        return [item.value for item in self.item_lines if item.selected]

    def get_selected_values(self) -> List[Any]:
        self._document = Document(text='\n'.join(line.text for line in self.item_lines))
        self._buffer = _LineJumpingBuffer(read_only=True, document=self._document)
        layout, self._item_selection_pane = self._create_layout()
        app = Application(key_bindings=self._create_key_bindings(), layout=layout)

        self._move_cursor_to_line(self._initial_cursor_item_index)
        app.run()

        return self._accepted_selection


def multiselect(messenger: Messenger, options: List[str], initial_selection: List[int], title: str,
                help: str, min_selection_count: int, colorize: bool) -> List[str]:
    assert len(options) >= min_selection_count

    menu = _MultiSelectPrompt(
        highlighted_style='bold fg:black bg:white' if colorize else '',
        header_style='bold fg:ansibrightgreen' if colorize else '',
        initial_cursor_index=initial_selection[0] if initial_selection else 0,
        min_selection_count=min_selection_count,
    )

    menu.add_header(title)

    for i, option in enumerate(options):
        menu.add_item(option, selected=i in initial_selection)

    menu.add_footer(help)

    messenger.produce_air()

    selected_options = menu.get_selected_values()
    if selected_options is None:
        raise KeyboardInterrupt

    messenger.request_air('\n')

    return selected_options
