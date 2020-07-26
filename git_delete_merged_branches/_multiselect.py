# Copyright (C) 2020 Sebastian Pipping <sebastian@pipping.org>
# Licensed under GPL v3 or later

from pick import Picker


class _PickerWithPreselection(Picker):
    def __init__(self, options, initial_selection=None, **kwargs):
        super().__init__(options, **kwargs)

        assert hasattr(self, 'all_selected')  # compat break detection
        if initial_selection is not None:
            self.all_selected = sorted(
                {i for i in initial_selection if isinstance(i, int) and 0 <= i < len(options)})
            if self.all_selected and kwargs.get('default_index') is None:
                self.index = self.all_selected[0]


def multiselect(options, initial_selection, title, min_selection_count):
    selection = _PickerWithPreselection(options, title=title, multiselect=True, indicator='▶',
                                        min_selection_count=min_selection_count,
                                        initial_selection=initial_selection).start()
    return [r[0] for r in selection]
