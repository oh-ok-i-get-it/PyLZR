"""The FIXTURES list in Settings → DMX: which lasers are patched, as one row
each (name, type, address, remove), plus Add and 'Open fixtures folder'.

The list only shows what it's given and says what you did: every edit
emits the whole new Patch (patch_edited), and the main window saves it and
shows the result again through set_patch(). Overlaps, running past channel
512 and missing types are allowed (they're saved, and shown under their
row); a name that's empty or already used goes back to the last good one.
"""

from collections.abc import Callable, Sequence

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QAbstractSpinBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea, QSpinBox, QVBoxLayout,
    QWidget,
)

from ..fixtures import Patch, PatchEntry, PatchError, PatchProblem
from ..fixtures.patch import UNIVERSE
from ..fixtures.vocabulary import MAX_NAME
from . import style, theme
from .panel_style import label
from .widgets import ElidedComboBox, ProblemLine, SectionTitle, set_role

ROW_H        = 22     # like the Art-Net row's inputs and buttons
SPACING      = 6      # between the controls of a row
ROW_GAP      = 4      # between rows
TYPE_W       = 210
ADDRESS_W    = 44
VISIBLE_ROWS = 5      # more rows than this scroll
FILE_LINES   = 3      # file problems shown; the rest are counted (all of them are in the log)

_NO_TYPES  = 'No fixture types: see the problems below.'
_ADD_TIP   = 'Add a fixture at the next free address.'

# (key, name, footprint) of a fixture type
TypeInfo = tuple[str, str, int]


def remove_box(parent: QWidget | None, entry: PatchEntry, type_name: str | None,
               footprint: int | None) -> tuple[QMessageBox, QPushButton]:
    """The 'Remove <name>?' question (not shown yet) and its Remove button.
    Cancel is the default, so Enter and Esc keep the fixture."""
    if type_name is None:
        detail = f'Its type "{entry.type}" isn\'t available.'
    else:
        detail = f'It\'s a {type_name} at channels {entry.address}–{entry.last(footprint)}.'
    box = QMessageBox(QMessageBox.Question, 'Remove fixture', f'Remove {entry.name}?', parent=parent)
    box.setInformativeText(detail)
    remove = box.addButton('Remove', QMessageBox.DestructiveRole)
    cancel = box.addButton(QMessageBox.Cancel)
    box.setDefaultButton(cancel)
    box.setEscapeButton(cancel)
    return box, remove


def ask_remove(parent: QWidget | None, entry: PatchEntry, type_name: str | None, footprint: int | None) -> bool:
    """Ask before removing a fixture; True only if Remove was clicked."""
    box, remove = remove_box(parent, entry, type_name, footprint)
    style.dark_title_bar(box)
    box.exec_()
    return box.clickedButton() is remove


def _button(text: str, icon: str, tip: str = '', icon_only: bool = False) -> QPushButton:
    button = QPushButton(text)
    button.setFixedHeight(ROW_H)
    set_role(button, 'small-button', **({'shape': 'icon'} if icon_only else {}))
    picture = style.icon(icon, theme.TEXT_DIM, size=12)
    if not picture.isNull():
        button.setIcon(picture)
        button.setIconSize(QSize(12, 12))
        if icon_only:
            button.setText('')
    if icon_only:
        button.setFixedWidth(ROW_H)
    button.setToolTip(tip)
    return button


class _Row(QWidget):
    """One fixture's controls, with its problem underneath (hidden when there's none)."""

    def __init__(self):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(2)
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(SPACING)

        self.name = QLineEdit()
        self.name.setMaxLength(MAX_NAME)
        self.name.setFixedHeight(ROW_H)
        set_role(self.name, 'input', kind='text')        # a name, in the UI font (IPs and numbers stay mono)
        self.name.setToolTip(f'The fixture\'s name (1–{MAX_NAME} characters, each one different)')

        self.type = ElidedComboBox()
        self.type.setFixedSize(TYPE_W, ROW_H)
        self.type.setToolTip('What kind of fixture it is (its binding)')

        self.address = QSpinBox()
        self.address.setRange(1, UNIVERSE)
        self.address.setButtonSymbols(QAbstractSpinBox.NoButtons)
        self.address.setKeyboardTracking(False)          # changes when typing ends, not on every digit
        self.address.setFixedSize(ADDRESS_W, ROW_H)
        set_role(self.address, 'input')
        self.address.setToolTip('Its first DMX channel (1–512), as set on the fixture')

        self.remove = _button('✕', 'x', 'Remove this fixture', icon_only=True)

        controls.addWidget(self.name, stretch=1)
        controls.addWidget(self.type)
        controls.addWidget(self.address)
        controls.addWidget(self.remove)
        outer.addLayout(controls)

        self.problem = ProblemLine()
        self.problem.hide()
        outer.addWidget(self.problem)

    def widgets(self) -> tuple[QWidget, ...]:
        return self.name, self.type, self.address, self.remove


class FixtureList(QWidget):
    """The FIXTURES list (see the module docstring).

    Signals:
        patch_edited(Patch)     — the patch after an edit (add, rename, type, address, remove)
        open_folder_requested() — 'Open fixtures folder' clicked
        size_changed()          — rows or problem lines came or went (the panel re-fits)

    Setters (they never emit patch_edited): set_types(), set_patch(),
    set_file_problems(). `confirm_remove(parent, entry, type name or None,
    footprint or None) -> bool` asks before a fixture is removed.
    """

    patch_edited          = pyqtSignal(object)
    open_folder_requested = pyqtSignal()
    size_changed          = pyqtSignal()

    def __init__(self, parent: QWidget | None = None,
                 confirm_remove: Callable[..., bool] = ask_remove):
        super().__init__(parent)
        self._confirm_remove = confirm_remove
        self._patch = Patch()
        self._types: dict[str, tuple[str, int]] = {}     # key -> (name, footprint), in list order
        self._problems: dict[int, str] = {}              # row -> what's wrong with that fixture
        self._notes: dict[int, str] = {}                 # row -> why the last rename was refused
        self._rows: list[_Row] = []
        self._shape = None                               # what size_changed compares
        self._build()
        self._update()

    # ── Layout ───────────────────────────────────────────────────────────

    def _build(self):
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(SectionTitle('FIXTURES', tone='dim'))
        top.addStretch(1)
        self._open_btn = _button('Open fixtures folder', 'folder-open',
                                 'Open the folder with your patch, fixture profiles and bindings. '
                                 'Changes to its files show the next time Settings opens.')
        self._open_btn.clicked.connect(lambda: self.open_folder_requested.emit())
        top.addWidget(self._open_btn)
        v.addLayout(top)

        self._header = QHBoxLayout()
        self._header.setContentsMargins(0, 0, 0, 0)
        self._header.setSpacing(SPACING)
        self._header.addWidget(label('Name'), stretch=1)
        for text, width in (('Type', TYPE_W), ('Address', ADDRESS_W + SPACING + ROW_H)):
            lbl = label(text)
            lbl.setFixedWidth(width)
            self._header.addWidget(lbl)
        self._header_widget = QWidget()
        self._header_widget.setLayout(self._header)
        v.addWidget(self._header_widget)

        self._empty = QLabel('No fixtures yet')
        set_role(self._empty, 'status')
        v.addWidget(self._empty)

        self._content = QWidget()
        self._rows_layout = QVBoxLayout(self._content)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(ROW_GAP)
        self._scroll = QScrollArea()
        set_role(self._scroll, 'plain-scroll')
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._scroll.setWidget(self._content)
        v.addWidget(self._scroll)

        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 0, 0, 0)
        self._add_btn = _button('Add fixture', 'plus')
        self._add_btn.clicked.connect(self._add)
        add_row.addWidget(self._add_btn)
        add_row.addStretch(1)
        v.addLayout(add_row)

        self._file_lines: list[ProblemLine] = []
        self._files_layout = QVBoxLayout()
        self._files_layout.setContentsMargins(0, 0, 0, 0)
        self._files_layout.setSpacing(2)
        v.addLayout(self._files_layout)

    # ── Setters ──────────────────────────────────────────────────────────

    def set_types(self, types: Sequence[TypeInfo]):
        """The fixture types that can be chosen: (key, name, footprint), in list order."""
        self._types = {key: (name, footprint) for key, name, footprint in types}
        self._update()

    def set_patch(self, patch: Patch, problems: Sequence[PatchProblem] = ()):
        """Show `patch`, with each problem under its fixture's row."""
        self._patch = patch
        index = {name: i for i, name in enumerate(patch.names)}
        self._problems = {index[p.name]: p.message for p in problems if p.name in index}
        self._notes = {}
        self._update()

    def set_file_problems(self, lines: Sequence[str]):
        """Files of yours (or shipped ones) that couldn't be used, one line each."""
        for line in self._file_lines:
            self._files_layout.removeWidget(line)
            line.hide()                                  # gone now, not when the deletion runs
            line.deleteLater()
        shown = list(lines[:FILE_LINES])
        if len(lines) > FILE_LINES:
            shown.append(f'… and {len(lines) - FILE_LINES} more (see the console)')
        self._file_lines = [ProblemLine(text) for text in shown]
        for line in self._file_lines:
            self._files_layout.addWidget(line)
        self._emit_if_resized()

    # ── Read-backs (what's shown) ────────────────────────────────────────

    def rows(self) -> list[tuple[str, str, int]]:
        """(name, type key, address) of each row, as shown."""
        return [(row.name.text(), row.type.currentData(), row.address.value()) for row in self._rows]

    def problem_texts(self) -> list[str | None]:
        """The problem shown under each row (None: no problem)."""
        return [row.problem.text() if row.problem.isVisibleTo(self) else None for row in self._rows]

    def types(self) -> list[tuple[str, str]]:
        """(key, name) of every type that can be chosen."""
        return [(key, name) for key, (name, _footprint) in self._types.items()]

    def file_problem_texts(self) -> list[str]:
        return [line.text() for line in self._file_lines]

    # ── Showing the patch ────────────────────────────────────────────────

    def _update(self):
        """Make the rows match the patch (signals blocked), then Add and the sizes."""
        entries = self._patch.entries
        while len(self._rows) < len(entries):
            self._rows_layout.addWidget(self._new_row(len(self._rows)))
        while len(self._rows) > len(entries):
            row = self._rows.pop()
            for widget in row.widgets():
                widget.blockSignals(True)
            self._rows_layout.removeWidget(row)
            row.deleteLater()
        for i, (row, entry) in enumerate(zip(self._rows, entries, strict=True)):
            self._show_entry(i, row, entry)
        self._update_add()
        self._fit_scroll()
        self._emit_if_resized()

    def _new_row(self, i: int) -> _Row:
        row = _Row()
        row.name.editingFinished.connect(lambda: self._rename(i))
        row.type.activated.connect(lambda _index: self._change_type(i))
        row.address.valueChanged.connect(lambda _value: self._change_address(i))
        row.remove.clicked.connect(lambda: self._remove(i))
        self._rows.append(row)
        return row

    def _show_entry(self, i: int, row: _Row, entry: PatchEntry):
        for widget in row.widgets():
            widget.blockSignals(True)
        if row.name.text() != entry.name:
            row.name.setText(entry.name)
        row.type.clear()
        for key, (name, _footprint) in self._types.items():
            row.type.addItem(name, key)
            row.type.setItemData(row.type.count() - 1, f'{name} ({key})', Qt.ToolTipRole)
        if entry.type not in self._types:
            row.type.addItem(f'{entry.type} (missing)', entry.type)
        row.type.setCurrentIndex(row.type.findData(entry.type))
        row.address.setValue(entry.address)
        for widget in row.widgets():
            widget.blockSignals(False)
        message = self._notes.get(i) or self._problems.get(i)
        row.problem.setText(message or '')
        row.problem.setVisible(bool(message))

    def _new_type(self) -> str | None:
        """The type for Add: the last fixture's, else the first one available."""
        if self._patch.entries and self._patch.entries[-1].type in self._types:
            return self._patch.entries[-1].type
        return next(iter(self._types), None)

    def _footprints(self) -> dict[str, int]:
        return {key: footprint for key, (_name, footprint) in self._types.items()}

    def _update_add(self):
        kind = self._new_type()
        if kind is None:
            self._add_btn.setEnabled(False)
            self._add_btn.setToolTip(_NO_TYPES)
            return
        name, footprint = self._types[kind]
        room = self._patch.next_free_address(footprint, self._footprints()) is not None
        self._add_btn.setEnabled(room)
        self._add_btn.setToolTip(_ADD_TIP if room else f'No room left in the universe for another {name}.')

    def _fit_scroll(self):
        """The scroll area is as tall as its rows, up to VISIBLE_ROWS rows; the
        column titles make room for the scroll bar when it shows."""
        has_rows = bool(self._rows)
        self._empty.setVisible(not has_rows)
        self._header_widget.setVisible(has_rows)
        self._scroll.setVisible(has_rows)
        if not has_rows:
            return
        for row in self._rows:
            row.ensurePolished()
        heights = [row.sizeHint().height() for row in self._rows]
        content = sum(heights) + ROW_GAP * (len(heights) - 1)
        first = heights[:VISIBLE_ROWS]
        limit = sum(first) + ROW_GAP * (len(first) - 1)          # the first rows, with their problems
        self._scroll.setFixedHeight(min(content, limit))
        scrolls = content > limit
        bar = self._scroll.verticalScrollBar().sizeHint().width() if scrolls else 0
        self._header.setContentsMargins(0, 0, bar, 0)

    def _emit_if_resized(self):
        shape = (len(self._rows), tuple(self.problem_texts()), len(self._file_lines))
        if shape != self._shape:
            self._shape = shape
            self.size_changed.emit()

    # ── Edits ────────────────────────────────────────────────────────────

    def _edited(self, patch: Patch):
        self._notes = {}
        self.patch_edited.emit(patch)

    def _add(self):
        kind = self._new_type()
        if kind is None:
            return
        address = self._patch.next_free_address(self._types[kind][1], self._footprints())
        if address is None:
            return
        self._edited(self._patch.with_fixture(PatchEntry(self._patch.next_name(), kind, address)))

    def _rename(self, i: int):
        entry, row = self._patch.entries[i], self._rows[i]
        text = row.name.text()
        if ' '.join(text.split()) == entry.name:
            if text != entry.name:
                row.name.setText(entry.name)                 # extra spaces tidied, nothing else changed
            return
        try:
            patch = self._patch.replaced(entry.name, PatchEntry(text, entry.type, entry.address))
        except PatchError as e:
            reason = e.message if text.strip() else 'a fixture needs a name'
            self._notes = {i: f'Not renamed: {reason}'}
            self._show_entry(i, row, entry)                  # puts the last good name back, with the reason
            self._fit_scroll()
            self._emit_if_resized()
            return
        self._edited(patch)

    def _change_type(self, i: int):
        entry = self._patch.entries[i]
        kind = self._rows[i].type.currentData()
        if kind != entry.type:
            self._edited(self._patch.replaced(entry.name, PatchEntry(entry.name, kind, entry.address)))

    def _change_address(self, i: int):
        entry = self._patch.entries[i]
        address = self._rows[i].address.value()
        if address != entry.address:
            self._edited(self._patch.replaced(entry.name, PatchEntry(entry.name, entry.type, address)))

    def _remove(self, i: int):
        entry = self._patch.entries[i]
        name, footprint = self._types.get(entry.type, (None, None))
        if self._confirm_remove(self, entry, name, footprint):
            self._edited(self._patch.without(entry.name))
