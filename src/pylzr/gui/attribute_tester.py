"""The tester's Attributes tab: drive one patched fixture through its
binding, attribute by attribute, live.

Everything shown is built from the chosen fixture's renderer, so the tab
works the same for any laser: a row for each attribute it supports, one
column per layer it has, its own choices in each dropdown, its extras in
THIS LASER, and its own pattern channels in the untagged pattern picker.

Nothing is in a fixture's state until you touch it: an untouched control
shows '—' and the fixture keeps its default there. Untagged patterns (raw
pattern-channel values) are for testing only; content asks for patterns by
category and scales (see fixtures/renderer.py).
"""

from dataclasses import dataclass, field
from typing import Any

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractSpinBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSlider, QSpinBox,
    QSizePolicy, QStackedWidget, QVBoxLayout, QWidget,
)

from ..fixtures import AttrKey, Kind, PatternEntry, PatternRequest, Renderer, Rig, Vocabulary
from ..fixtures.attributes import DEFAULT_LAYER
from ..fixtures.mappings import OFF_CHOICES
from ..fixtures.renderer import PatternChannel
from ..fixtures.vocabulary import LEVELS, level_value
from . import theme
from .panel_style import label
from .widgets import Card, ElidedComboBox, SectionTitle, set_props, set_role

LABEL_W   = 104     # the attribute names' column
READOUT_W = 56      # '+100%', 'ignored' in the mono font
GAP       = 12      # between the grid's columns
SNAP      = 3       # a bipolar slider within ±3 % of the centre snaps to it

# Where each core attribute goes; core attributes not listed go to MOTION,
# a binding's extras (x_…) to THIS LASER
CARDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ('SHAPE',    ('size', 'zoom', 'rot_x', 'rot_y', 'rot_z')),
    ('POSITION', ('pos_x', 'pos_y', 'move_x', 'move_y')),
    ('COLOUR',   ('color', 'color_effect', 'color_speed', 'gradient_speed')),
    ('MOTION',   ('spin_x', 'spin_y', 'spin_z', 'zoom_motion', 'zoom_style', 'wave_x', 'wave_y', 'strobe',
                  'draw_style', 'scan_speed')),
)
EXTRAS_CARD = 'THIS LASER'
TOP_ROW     = ('power',)            # shown as the Power toggle, not in the grid
NOT_SHOWN   = (Kind.EVENT,)         # events (blackout) are for scenes

_WARNING  = 'Values go out live. Keep the laser aimed safely before changing anything.'
_EMPTY    = 'No fixtures patched yet: add one in Settings → DMX.'
_IGNORED  = 'Ignored: another setting on the same channel wins (it comes first in the binding).'
_NO_TAGS  = 'No tagged patterns yet: see the Patterns tab.'


def attribute_label(name: str) -> str:
    """'pos_x' → 'Pos X', 'x_flowing_water' → 'Flowing water'."""
    words = name.removeprefix('x_').split('_')
    words = [w.upper() if len(w) == 1 else w for w in words]
    words[0] = words[0][:1].upper() + words[0][1:]
    return ' '.join(words)


def choice_label(option: str) -> str:
    return option.replace('_', ' ')


# ── Controls that leave the page scrolling ──────────────────────────────────
# A wheel over a control only changes it once it has focus (clicked or tabbed
# to); otherwise the page scrolls, so scrolling never moves a laser setting.

class _Slider(QSlider):
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class _Combo(ElidedComboBox):
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class _Spin(QSpinBox):
    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


def _combo(items: list[tuple[str, Any]], tip: str = '') -> _Combo:
    combo = _Combo()
    combo.setFocusPolicy(Qt.StrongFocus)
    for text, data in items:
        combo.addItem(text, data)
    combo.setToolTip(tip)
    return combo


def _select(combo: _Combo, data: Any):
    combo.blockSignals(True)
    combo.setCurrentIndex(max(0, combo.findData(data)))
    combo.blockSignals(False)


# ── Cells: one attribute on one layer ───────────────────────────────────────

class _Cell(QWidget):
    """A control for one attribute on one layer. value() is None while unset.
    Cells take their column's width, so every layer's column is as wide."""

    changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def value(self) -> Any:
        raise NotImplementedError

    def set_value(self, value: Any):
        """Show `value` (None: unset) without emitting."""
        raise NotImplementedError

    def set_ignored(self, ignored: bool):
        raise NotImplementedError


class _SliderCell(_Cell):
    """continuous: 0–100 %; bipolar: −100…+100 %, snapping to 0 near the centre."""

    def __init__(self, bipolar: bool, tip: str):
        super().__init__()
        self.bipolar = bipolar
        self._set = False
        self._ignored = False
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.slider = _Slider(Qt.Horizontal)
        self.slider.setRange(-100 if bipolar else 0, 100)
        self.slider.setPageStep(10)
        self.slider.setFocusPolicy(Qt.StrongFocus)
        self.slider.setToolTip(tip)
        self.slider.valueChanged.connect(self._moved)
        self.readout = QLabel()
        self.readout.setFixedWidth(READOUT_W)
        self.readout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        set_role(self.readout, 'readout')
        row.addWidget(self.slider, stretch=1)
        row.addWidget(self.readout)
        self._show()

    def _moved(self, position: int):
        if self.bipolar and position != 0 and abs(position) <= SNAP:
            self.slider.blockSignals(True)
            self.slider.setValue(0)
            self.slider.blockSignals(False)
        self._set = True
        self._show()
        self.changed.emit()

    def value(self) -> float | None:
        return self.slider.value() / 100 if self._set else None

    def set_value(self, value: float | None):
        self.slider.blockSignals(True)
        self._set = value is not None
        self.slider.setValue(round(value * 100) if value is not None else 0)
        self.slider.blockSignals(False)
        self._show()

    def set_ignored(self, ignored: bool):
        if ignored != self._ignored:
            self._ignored = ignored
            self._show()

    def _show(self):
        position = self.slider.value()
        if self._ignored:
            text = 'ignored'
        elif not self._set:
            text = '—'
        elif self.bipolar and position:
            text = f'{position:+d}%'
        else:
            text = f'{position}%'
        self.readout.setText(text)
        self.readout.setToolTip(_IGNORED if self._ignored else '')
        set_props(self.readout, state='ignored' if self._ignored else '')


class _OptionCell(_Cell):
    """A dropdown: '—' (unset), then the choices this fixture offers."""

    def __init__(self, choices: list[str], tip: str):
        super().__init__()
        self._tip = tip
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.combo = _combo([('—', None)] + [(choice_label(c), c) for c in choices], tip)
        self.combo.currentIndexChanged.connect(lambda _index: self.changed.emit())
        row.addWidget(self.combo)

    def value(self) -> str | None:
        return self.combo.currentData()

    def set_value(self, value: str | None):
        _select(self.combo, value)

    def set_ignored(self, ignored: bool):
        set_props(self.combo, state='ignored' if ignored else '')
        self.combo.setToolTip(_IGNORED if ignored else self._tip)


# ── The pattern cell ────────────────────────────────────────────────────────

SOURCES = (('None', 'none'), ('By category', 'category'), ('By name', 'name'), ('Untagged', 'raw'))


def _default_raw(channels: tuple[PatternChannel, ...], none: dict[str, int]) -> dict[str, int]:
    """A first untagged pick that shows something: on each channel, the start of
    the first segment that isn't the "no pattern" value."""
    raw = {}
    for channel in channels:
        off = none.get(channel.name)
        segment = next((s for s in channel.segments if off is None or not s.contains(off)), channel.segments[0])
        raw[channel.name] = segment.start
    return raw


class _PatternCell(_Cell):
    """One layer's pattern: none, a tagged request (by category and scales, or
    by name), or an untagged pick of raw pattern-channel values.
    value() is (request or None, raw values or None)."""

    def __init__(self, renderer: Renderer, layer: str, vocabulary: Vocabulary):
        super().__init__()
        self._library = renderer.library
        self._channels = renderer.pattern_channels(layer)
        self._vocabulary = vocabulary
        tagged = bool(self._library.entries)

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        self.source = _combo([(text, data) for text, data in SOURCES],
                             'None: this layer is dark. By category or by name: a tagged pattern. '
                             'Untagged: any pattern, by its channel values (for testing).')
        for i, (_text, data) in enumerate(SOURCES):
            if data in ('category', 'name') and not tagged:
                self.source.model().item(i).setEnabled(False)
                self.source.setItemData(i, _NO_TAGS, Qt.ToolTipRole)
        self.source.currentIndexChanged.connect(self._source_changed)
        v.addWidget(self.source)

        self.pages = QStackedWidget()
        self.pages.addWidget(QWidget())                         # none
        self.pages.addWidget(self._category_page())
        self.pages.addWidget(self._name_page())
        self.pages.addWidget(self._raw_page())
        v.addWidget(self.pages)

        self.matched = QLabel()
        set_role(self.matched, 'status')
        self.matched.setWordWrap(True)
        v.addWidget(self.matched)
        self._show_page()

    # pages

    def _form_row(self, text: str, widget: QWidget, tip: str = '') -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        lbl = label(text)
        lbl.setFixedWidth(72)
        lbl.setToolTip(tip)
        row.addWidget(lbl)
        row.addWidget(widget, stretch=1)
        return row

    def _category_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        counts = {c: len(self._library.in_category(c)) for c in self._vocabulary.categories}
        self.category = _combo([(f'{c} ({counts[c]})', c) for c in self._vocabulary.categories],
                               'Tagged patterns in each category, in brackets')
        self.category.currentIndexChanged.connect(lambda _i: self.changed.emit())
        v.addLayout(self._form_row('Category', self.category))
        self.levels: dict[str, _Combo] = {}
        for scale in self._vocabulary.scales:
            combo = _combo([('any', None)] + [(str(n), level_value(n)) for n in range(1, LEVELS + 1)],
                           f'1 {scale.low} … {LEVELS} {scale.high}')
            combo.currentIndexChanged.connect(lambda _i: self.changed.emit())
            self.levels[scale.name] = combo
            v.addLayout(self._form_row(attribute_label(scale.name), combo, f'{scale.low} … {scale.high}'))
        return page

    def _name_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        self.entry = _combo([(f'{e.name} ({e.category})', e.name) for e in self._library.entries])
        self.entry.currentIndexChanged.connect(lambda _i: self.changed.emit())
        v.addLayout(self._form_row('Pattern', self.entry))
        return page

    def _raw_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(4)
        self.raw_parts: dict[str, tuple[_Combo, _Spin]] = {}
        for channel in self._channels:
            segments = _combo([(f'{s.label} · {s.start}–{s.end}' if s.end > s.start else f'{s.label} · {s.start}', i)
                               for i, s in enumerate(channel.segments)], f'What {channel.name} does')
            spin = _Spin()
            spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
            spin.setKeyboardTracking(False)
            spin.setFocusPolicy(Qt.StrongFocus)
            spin.setFixedWidth(44)
            spin.setAlignment(Qt.AlignCenter)
            set_role(spin, 'input')
            spin.setToolTip(f'The DMX value sent on {channel.name}')
            segments.currentIndexChanged.connect(lambda _i, ch=channel: self._segment_chosen(ch))
            spin.valueChanged.connect(lambda _v: self.changed.emit())
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(6)
            row.addWidget(segments, stretch=1)
            row.addWidget(spin)
            name = label(channel.name)
            v.addWidget(name)
            v.addLayout(row)
            self.raw_parts[channel.name] = (segments, spin)
        return page

    # behaviour

    def _source(self) -> str:
        return self.source.currentData()

    def _source_changed(self, _index: int):
        if self._source() == 'raw':
            self._set_raw(_default_raw(self._channels, dict(self._library.none)))
        self._show_page()
        self.changed.emit()

    def _show_page(self):
        self.pages.setCurrentIndex([data for _text, data in SOURCES].index(self._source()))
        self.pages.setVisible(self._source() != 'none')

    def _segment_chosen(self, channel: PatternChannel):
        segments, spin = self.raw_parts[channel.name]
        segment = channel.segments[segments.currentData()]
        spin.blockSignals(True)
        spin.setRange(segment.start, segment.end)
        spin.setValue(segment.start)
        spin.blockSignals(False)
        self.changed.emit()

    def _set_raw(self, values: dict[str, int]):
        for channel in self._channels:
            segments, spin = self.raw_parts[channel.name]
            value = values[channel.name]
            index = next(i for i, s in enumerate(channel.segments) if s.contains(value))
            segment = channel.segments[index]
            for widget in (segments, spin):
                widget.blockSignals(True)
            segments.setCurrentIndex(index)
            spin.setRange(segment.start, segment.end)
            spin.setValue(value)
            for widget in (segments, spin):
                widget.blockSignals(False)

    def value(self) -> tuple[PatternRequest | None, dict[str, int] | None]:
        source = self._source()
        if source == 'category' and self.category.count():
            scales = {name: combo.currentData() for name, combo in self.levels.items()
                      if combo.currentData() is not None}
            return PatternRequest.of(self.category.currentData(), **scales), None
        if source == 'name' and self.entry.count():
            return PatternRequest.entry(self.entry.currentData()), None
        if source == 'raw':
            return None, {name: spin.value() for name, (_segments, spin) in self.raw_parts.items()}
        return None, None

    def set_value(self, value: tuple[PatternRequest | None, dict[str, int] | None]):
        request, raw = value if value is not None else (None, None)
        if raw is not None:
            source = 'raw'
            self._set_raw(raw)
        elif request is not None and request.name:
            source = 'name'
            _select(self.entry, request.name)
        elif request is not None:
            source = 'category'
            _select(self.category, request.category)
            for name, combo in self.levels.items():
                _select(combo, request.scale_values.get(name))
        else:
            source = 'none'
        _select(self.source, source)
        self._show_page()

    def set_ignored(self, ignored: bool):
        pass                                        # a raw pick replaces the request on purpose

    def set_matched(self, entry: PatternEntry | None):
        source = self._source()
        if source == 'none':
            text = 'No pattern: this layer is dark.'
        elif source == 'raw':
            text = f'Tagged as {entry.name} ({entry.category})' if entry else 'Not tagged yet'
        elif entry is None:
            text = 'Nothing tagged in this category' if source == 'category' else 'Not found'
        else:
            text = f'Matched: {entry.name}'
        self.matched.setText(text)


# ── The tab ─────────────────────────────────────────────────────────────────

@dataclass
class _FixtureState:
    """What's set on one fixture while the window is open."""

    type:   str
    values: dict[AttrKey, Any] = field(default_factory=dict)
    raw:    dict[str, dict[str, int]] = field(default_factory=dict)    # layer → untagged pattern


class AttributeTester(QWidget):
    """The Attributes tab (see the module docstring). A tester tab:

        channels_changed(int, list) — the chosen fixture's first channel and
                                      values; (1, []) when there's nothing to send
        resend()                    — emit channels_changed for what's shown
        reset()                     — every fixture back to unset, without emitting

    set_rig() gives it the patch and what renders it (and the pattern words);
    call it again whenever they change.
    """

    channels_changed = pyqtSignal(int, list)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._rig: Rig | None = None
        self._vocabulary = Vocabulary()
        self._states: dict[str, _FixtureState] = {}
        self._cells: dict[AttrKey, _Cell] = {}
        self._patterns: dict[str, _PatternCell] = {}
        self._build()
        self._show_fixture(None)

    # ── Layout ───────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(6)
        self._fixture_label = label('Fixture')
        set_role(self._fixture_label, 'label', tone='light')
        top.addWidget(self._fixture_label)
        self._fixture = _combo([], 'Which patched fixture to drive (Settings → DMX)')
        self._fixture.setMinimumWidth(180)
        self._fixture.currentIndexChanged.connect(self._fixture_chosen)
        top.addWidget(self._fixture)
        top.addSpacing(8)
        self._power_label = label('Power')
        set_role(self._power_label, 'label', tone='light')
        top.addWidget(self._power_label)
        self._power = QPushButton('OFF')
        self._power.setCheckable(True)
        self._power.setFixedHeight(22)
        set_role(self._power, 'small-button')
        self._power.setToolTip('Laser output off or on')
        self._power.toggled.connect(self._power_toggled)
        top.addWidget(self._power)
        top.addStretch(1)
        self._reset_btn = QPushButton('Reset')
        set_role(self._reset_btn, 'small-button')
        self._reset_btn.setToolTip('Every attribute of this fixture back to unset (its defaults)')
        self._reset_btn.clicked.connect(self._reset_fixture)
        top.addWidget(self._reset_btn)
        root.addLayout(top)

        warning = QLabel(_WARNING)
        warning.setObjectName('Warning')
        set_role(warning, 'warning')
        warning.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        root.addWidget(warning)

        self._empty = QLabel(_EMPTY)
        set_role(self._empty, 'status')
        self._empty.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._empty.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)   # takes the grid's room
        root.addWidget(self._empty)

        self._header = QHBoxLayout()
        self._header.setSpacing(GAP)
        self._header_widget = QWidget()
        self._header_widget.setLayout(self._header)
        root.addWidget(self._header_widget)

        self._scroll = QScrollArea()
        set_role(self._scroll, 'plain-scroll')
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.verticalScrollBar().rangeChanged.connect(self._fit_header)
        root.addWidget(self._scroll, stretch=1)

    def _build_grid(self, renderer: Renderer, state: _FixtureState):
        """Cards of rows for `renderer`'s attributes, showing `state`."""
        self._cells, self._patterns = {}, {}
        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(theme.GAP)
        layers = renderer.layers

        if renderer.library is not None and any(renderer.supports(AttrKey('pattern', la)) for la in layers):
            grid = self._card(v, 'PATTERN', len(layers))
            self._row_label(grid, 0, 'Pattern', 'Which pattern each layer shows')
            for col, layer in enumerate(layers, start=1):
                cell = _PatternCell(renderer, layer, self._vocabulary)
                cell.set_value((state.values.get(AttrKey('pattern', layer)), state.raw.get(layer)))
                cell.changed.connect(lambda layer=layer, cell=cell: self._pattern_changed(layer, cell))
                grid.addWidget(cell, 0, col, Qt.AlignTop)
                self._patterns[layer] = cell

        for title, names in self._card_rows(renderer):
            grid = self._card(v, title, len(layers))
            for row, name in enumerate(names):
                attribute = renderer.attributes[name]
                self._row_label(grid, row, attribute_label(name), attribute.description)
                for col, layer in enumerate(layers, start=1):
                    if not attribute.layered and layer != DEFAULT_LAYER:
                        continue
                    key = AttrKey(name, layer if attribute.layered else DEFAULT_LAYER)
                    if not renderer.supports(key):
                        dash = QLabel('—')
                        set_role(dash, 'status')
                        dash.setToolTip(f'Layer {layer.upper()} has no {attribute_label(name).lower()}')
                        grid.addWidget(dash, row, col)
                        continue
                    cell = self._make_cell(renderer, key)
                    cell.set_value(state.values.get(key))
                    cell.changed.connect(lambda key=key, cell=cell: self._cell_changed(key, cell))
                    grid.addWidget(cell, row, col)
                    self._cells[key] = cell
        v.addStretch(1)
        old = self._scroll.takeWidget()
        if old is not None:
            old.deleteLater()
        self._scroll.setWidget(content)

        self._fill_header(layers)

    def _card_rows(self, renderer: Renderer) -> list[tuple[str, list[str]]]:
        """(card title, attribute names) for every attribute some layer supports."""
        def shown(name: str) -> bool:
            attribute = renderer.attributes[name]
            return (name not in TOP_ROW and name != 'pattern' and attribute.kind not in NOT_SHOWN
                    and any(renderer.supports(AttrKey(name, layer)) for layer in renderer.layers))
        names = [a.name for a in renderer.attributes if shown(a.name)]
        placed = {name for _title, listed in CARDS for name in listed}
        cards = []
        for title, listed in CARDS:
            rows = [n for n in listed if n in names]
            if title == 'MOTION':
                rows += [n for n in names if n not in placed and not renderer.attributes[n].is_extra]
            if rows:
                cards.append((title, rows))
        extras = [n for n in names if renderer.attributes[n].is_extra]
        if extras:
            cards.append((EXTRAS_CARD, extras))
        return cards

    def _card(self, parent: QVBoxLayout, title: str, columns: int) -> QGridLayout:
        """A card whose grid has the label column and `columns` equal layer
        columns (the same in every card, so they line up down the page)."""
        grid = QGridLayout()
        grid.setHorizontalSpacing(GAP)
        grid.setVerticalSpacing(6)
        grid.setColumnMinimumWidth(0, LABEL_W)
        for column in range(1, columns + 1):
            grid.setColumnStretch(column, 1)
        card = Card(title, tone='dim')
        card.addLayout(grid)
        parent.addWidget(card)
        return grid

    def _row_label(self, grid: QGridLayout, row: int, text: str, tip: str):
        lbl = label(text)
        lbl.setFixedWidth(LABEL_W)
        lbl.setToolTip(tip)
        grid.addWidget(lbl, row, 0, Qt.AlignTop if text == 'Pattern' else Qt.AlignVCenter)

    def _make_cell(self, renderer: Renderer, key: AttrKey) -> _Cell:
        attribute = renderer.attributes[key.name]
        if attribute.kind == Kind.OPTION:
            offered = renderer.choices(key)
            choices = [o for o in attribute.options if o in offered or o in OFF_CHOICES]
            return _OptionCell(choices, attribute.description)
        return _SliderCell(attribute.kind == Kind.BIPOLAR, attribute.description)

    def _fill_header(self, layers: tuple[str, ...]):
        """Column titles over the layers' columns (they stay put while the grid scrolls)."""
        while self._header.count():
            item = self._header.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()                    # gone now, not when the deletion runs
                item.widget().deleteLater()
        self._header.addSpacing(LABEL_W + GAP)          # no spacing is added next to a spacer
        self._fit_header()
        self._layer_titles = []
        for layer in layers:
            title = SectionTitle(f'LAYER {layer.upper()}', tone='dim')
            self._header.addWidget(title, stretch=1)
            self._layer_titles.append(title)

    def _fit_header(self, *_range):
        """Line the column titles up with the cards' columns: a card's padding
        and border on each side, and room for the scroll bar while it shows."""
        pad = theme.CARD_PAD_X + 1
        bar = self._scroll.verticalScrollBar()
        self._header.setContentsMargins(pad, 0, pad + (bar.sizeHint().width() if bar.maximum() > 0 else 0), 0)

    # ── Fixtures ─────────────────────────────────────────────────────────

    def set_rig(self, rig: Rig, vocabulary: Vocabulary | None = None):
        """The patch and its renderers (and the pattern words). Fixtures that
        are gone or have a new type lose what was set on them."""
        self._rig = rig
        if vocabulary is not None:
            self._vocabulary = vocabulary
        for name in list(self._states):
            entry = rig.patch.entry(name)
            if entry is None or entry.name not in rig.usable or entry.type != self._states[name].type:
                del self._states[name]
        current = self.fixture()
        if current not in rig.usable:
            current = rig.usable[0] if rig.usable else None
        self._fixture.blockSignals(True)
        self._fixture.clear()
        for name in rig.usable:
            self._fixture.addItem(name, name)
        self._fixture.setCurrentIndex(self._fixture.findData(current))
        self._fixture.blockSignals(False)
        self._show_fixture(current)
        if self.isVisible():
            self.resend()

    def fixture(self) -> str | None:
        """The fixture being driven (None: nothing patched)."""
        return self._fixture.currentData()

    def _fixture_chosen(self, _index: int):
        self._show_fixture(self.fixture())
        self.resend()

    def _state(self, name: str) -> _FixtureState:
        if name not in self._states:
            self._states[name] = _FixtureState(self._rig.patch.entry(name).type)
        return self._states[name]

    def _show_fixture(self, name: str | None):
        has = name is not None and self._rig is not None
        for widget in (self._header_widget, self._scroll, self._reset_btn, self._fixture, self._fixture_label):
            widget.setVisible(has)
        self._empty.setVisible(not has)
        if not has:
            self._power_label.hide()
            self._power.hide()
            self._cells, self._patterns = {}, {}
            return
        renderer = self._rig.renderer(name)
        state = self._state(name)
        power = renderer.supports('power')
        self._power_label.setVisible(power)
        self._power.setVisible(power)
        self._power.blockSignals(True)
        self._power.setChecked(state.values.get(AttrKey('power')) == 'on')
        self._power.setText('ON' if self._power.isChecked() else 'OFF')
        self._power.blockSignals(False)
        self._build_grid(renderer, state)
        self._render()                                  # marks and matches show at once, nothing is sent

    # ── Edits ────────────────────────────────────────────────────────────

    def _set(self, key: AttrKey, value: Any):
        state = self._state(self.fixture())
        if value is None:
            state.values.pop(key, None)
        else:
            state.values[key] = value

    def _cell_changed(self, key: AttrKey, cell: _Cell):
        self._set(key, cell.value())
        self.resend()

    def _pattern_changed(self, layer: str, cell: _PatternCell):
        request, raw = cell.value()
        self._set(AttrKey('pattern', layer), request)
        state = self._state(self.fixture())
        if raw is None:
            state.raw.pop(layer, None)
        else:
            state.raw[layer] = raw
        self.resend()

    def _power_toggled(self, on: bool):
        self._power.setText('ON' if on else 'OFF')
        self._set(AttrKey('power'), 'on' if on else 'off')
        self.resend()

    def _reset_fixture(self):
        name = self.fixture()
        if name is None:
            return
        self._states.pop(name, None)
        self._show_fixture(name)
        self.resend()

    # ── Tester-tab protocol ──────────────────────────────────────────────

    def resend(self):
        start, values = self._render()
        self.channels_changed.emit(start, values)

    def _render(self) -> tuple[int, list[int]]:
        """(first channel, values) for the chosen fixture, marking what's
        ignored and what each layer's pattern matched; (1, []) when there's
        nothing to send (that clears the override layer)."""
        name = self.fixture()
        if name is None or self._rig is None:
            return 1, []
        state = self._state(name)
        start, result = self._rig.render_fixture(name, state.values, state.raw)
        for key, cell in self._cells.items():
            cell.set_ignored(key in result.ignored)
        for layer, cell in self._patterns.items():
            cell.set_matched(result.patterns.get(layer))
        return start, list(result.values)

    def reset(self):
        self._states.clear()
        self._show_fixture(self.fixture() if self._rig is not None else None)

    # ── Read-backs (for tests) ───────────────────────────────────────────

    def cell(self, key: 'AttrKey | str') -> _Cell | None:
        return self._cells.get(AttrKey.parse(key))

    def pattern_cell(self, layer: str = DEFAULT_LAYER) -> _PatternCell | None:
        return self._patterns.get(layer)

    def card_rows(self) -> dict[str, list[str]]:
        """{card title: attribute names}, as shown."""
        if self.fixture() is None:
            return {}
        rows = dict(self._card_rows(self._rig.renderer(self.fixture())))
        if self._patterns:
            rows = {'PATTERN': ['pattern'], **rows}
        return rows

    def state(self) -> dict[str, Any]:
        """The chosen fixture's attribute state, as {'size@b': 0.5, …}."""
        name = self.fixture()
        return {} if name is None else {str(k): v for k, v in self._state(name).values.items()}

    def raw_patterns(self) -> dict[str, dict[str, int]]:
        name = self.fixture()
        return {} if name is None else dict(self._state(name).raw)
