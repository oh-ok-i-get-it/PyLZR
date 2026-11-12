"""The FIXTURES list in Settings → DMX on its own (gui/fixture_list.py):
rows, Add's suggestions, renaming, type and address changes, removing (after
asking), problems under their rows, and file problems."""

import pytest
from PyQt5.QtWidgets import QMessageBox

from pylzr.fixtures import Patch, PatchEntry, PatchProblem
from pylzr.gui import FixtureList
from pylzr.gui.fixture_list import FILE_LINES, VISIBLE_ROWS, remove_box

GRUOLIN = 'gruolin/rgb-beam-36ch'
SMALL   = 'acme/small'
TYPES   = [(GRUOLIN, 'Gruolin RGB Beam (36ch)', 36), (SMALL, 'Small (4ch)', 4)]


class Confirm:
    """Stands in for the 'Remove …?' question: records what was asked, answers `answer`."""

    def __init__(self, answer=True):
        self.answer, self.asked = answer, []

    def __call__(self, parent, entry, type_name, footprint):
        self.asked.append((entry.name, type_name, footprint))
        return self.answer


def patch(*entries):
    return Patch(tuple(PatchEntry(*e) for e in entries))


def two_gruolins():
    return patch(('Laser L', GRUOLIN, 1), ('Laser R', GRUOLIN, 37))


@pytest.fixture
def confirm():
    return Confirm()


@pytest.fixture
def fl(qapp, confirm):
    widget = FixtureList(confirm_remove=confirm)
    widget.set_types(TYPES)
    return widget


def capture(signal):
    received = []
    signal.connect(lambda *args: received.append(args[0] if args else None))
    return received


def rename(fl, row, text):
    """Type a name and press Enter, as a user would."""
    fl._rows[row].name.setText(text)
    fl._rows[row].name.editingFinished.emit()


def choose_type(fl, row, key):
    combo = fl._rows[row].type
    combo.setCurrentIndex(combo.findData(key))
    combo.activated.emit(combo.currentIndex())


# ── Showing ──────────────────────────────────────────────────────────────

def test_rows_show_the_patch_and_setters_emit_nothing(fl):
    edited = capture(fl.patch_edited)
    fl.set_patch(two_gruolins())
    assert fl.rows() == [('Laser L', GRUOLIN, 1), ('Laser R', GRUOLIN, 37)]
    assert fl.types() == [(GRUOLIN, 'Gruolin RGB Beam (36ch)'), (SMALL, 'Small (4ch)')]
    assert fl.problem_texts() == [None, None]
    assert edited == []


def test_empty_list_says_so(fl):
    assert fl.rows() == []
    assert fl._empty.isVisibleTo(fl) and not fl._scroll.isVisibleTo(fl) and not fl._header_widget.isVisibleTo(fl)
    fl.set_patch(two_gruolins())
    assert not fl._empty.isVisibleTo(fl) and fl._scroll.isVisibleTo(fl)


def test_type_dropdown_names_each_type(fl):
    fl.set_patch(two_gruolins())
    combo = fl._rows[0].type
    assert [combo.itemText(i) for i in range(combo.count())] == ['Gruolin RGB Beam (36ch)', 'Small (4ch)']
    assert combo.currentData() == GRUOLIN


def test_fewer_rows_after_a_smaller_patch(fl):
    fl.set_patch(two_gruolins())
    fl.set_patch(patch(('Solo', SMALL, 100)))
    assert fl.rows() == [('Solo', SMALL, 100)]


# ── Add ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('before, added', [
    ((), ('Laser 1', GRUOLIN, 1)),                                          # the first type
    ((('Laser 1', GRUOLIN, 1),), ('Laser 2', GRUOLIN, 37)),
    ((('Laser L', GRUOLIN, 1), ('Laser R', GRUOLIN, 37)), ('Laser 1', GRUOLIN, 73)),
    ((('Laser 1', SMALL, 1),), ('Laser 2', SMALL, 5)),                      # the last fixture's type
    ((('Laser 1', 'gone/laser', 1),), ('Laser 2', GRUOLIN, 2)),             # … if it's available
])
def test_add_suggests_name_address_and_type(fl, before, added):
    fl.set_patch(patch(*before))
    edited = capture(fl.patch_edited)
    fl._add_btn.click()
    assert edited == [patch(*before, added)]


def test_add_needs_a_type(fl):
    fl.set_types([])
    assert not fl._add_btn.isEnabled() and 'No fixture types' in fl._add_btn.toolTip()
    fl.set_types(TYPES)
    assert fl._add_btn.isEnabled()


def test_add_needs_room(fl):
    fl.set_patch(patch(*((f'L{i}', GRUOLIN, 1 + 36 * i) for i in range(14))))     # 504 channels used
    assert not fl._add_btn.isEnabled()
    assert fl._add_btn.toolTip() == 'No room left in the universe for another Gruolin RGB Beam (36ch).'
    fl.set_patch(patch(*((f'L{i}', GRUOLIN, 1 + 36 * i) for i in range(13))))
    assert fl._add_btn.isEnabled()


# ── Rename ───────────────────────────────────────────────────────────────

def test_rename(fl):
    fl.set_patch(two_gruolins())
    edited = capture(fl.patch_edited)
    rename(fl, 1, '  Laser   Right ')
    assert edited == [patch(('Laser L', GRUOLIN, 1), ('Laser Right', GRUOLIN, 37))]


def test_unchanged_name_emits_nothing_and_is_tidied(fl):
    fl.set_patch(two_gruolins())
    edited = capture(fl.patch_edited)
    rename(fl, 0, ' Laser  L ')
    assert edited == [] and fl.rows()[0][0] == 'Laser L'


@pytest.mark.parametrize('text, reason', [
    ('', 'Not renamed: a fixture needs a name'),
    ('   ', 'Not renamed: a fixture needs a name'),
    ('laser l', 'Not renamed: the name "laser l" is already used'),
])
def test_bad_name_goes_back_and_says_why(fl, text, reason):
    fl.set_patch(two_gruolins())
    edited = capture(fl.patch_edited)
    rename(fl, 1, text)
    assert edited == []
    assert fl.rows()[1][0] == 'Laser R'
    assert fl.problem_texts() == [None, reason]


def test_the_reason_goes_with_the_next_edit(fl):
    fl.set_patch(two_gruolins())
    rename(fl, 1, '')
    fl.patch_edited.connect(fl.set_patch)            # as the window does: show what was saved
    rename(fl, 1, 'Laser 2')
    assert fl.problem_texts() == [None, None] and fl.rows()[1][0] == 'Laser 2'


def test_name_is_at_most_32_characters(fl):
    fl.set_patch(two_gruolins())
    assert fl._rows[0].name.maxLength() == 32


# ── Type and address ─────────────────────────────────────────────────────

def test_change_type(fl):
    fl.set_patch(two_gruolins())
    edited = capture(fl.patch_edited)
    choose_type(fl, 1, SMALL)
    assert edited == [patch(('Laser L', GRUOLIN, 1), ('Laser R', SMALL, 37))]
    choose_type(fl, 0, GRUOLIN)                                             # the same type: nothing
    assert len(edited) == 1


def test_change_address_even_onto_another_fixture(fl):
    fl.set_patch(two_gruolins())
    edited = capture(fl.patch_edited)
    fl._rows[1].address.setValue(30)                                        # overlaps: saved, then flagged
    assert edited == [patch(('Laser L', GRUOLIN, 1), ('Laser R', GRUOLIN, 30))]


def test_address_box(fl):
    fl.set_patch(two_gruolins())
    box = fl._rows[0].address
    assert (box.minimum(), box.maximum()) == (1, 512) and not box.keyboardTracking()


def test_a_missing_type_is_kept(fl):
    fl.set_patch(patch(('Old', 'gone/laser', 10)), [PatchProblem('Old', 'its type "gone/laser" isn\'t available')])
    combo = fl._rows[0].type
    assert combo.currentData() == 'gone/laser' and combo.currentText() == 'gone/laser (missing)'
    assert fl.problem_texts() == ['its type "gone/laser" isn\'t available']
    edited = capture(fl.patch_edited)
    fl._rows[0].address.setValue(20)
    assert edited == [patch(('Old', 'gone/laser', 20))]


# ── Remove ───────────────────────────────────────────────────────────────

def test_remove_asks_first(fl, confirm):
    fl.set_patch(two_gruolins())
    edited = capture(fl.patch_edited)
    fl._rows[1].remove.click()
    assert confirm.asked == [('Laser R', 'Gruolin RGB Beam (36ch)', 36)]
    assert edited == [patch(('Laser L', GRUOLIN, 1))]


def test_cancelled_remove_keeps_the_fixture(fl, confirm):
    confirm.answer = False
    fl.set_patch(two_gruolins())
    edited = capture(fl.patch_edited)
    fl._rows[0].remove.click()
    assert confirm.asked == [('Laser L', 'Gruolin RGB Beam (36ch)', 36)]
    assert edited == [] and len(fl.rows()) == 2


def test_remove_question(qapp):
    box, remove = remove_box(None, PatchEntry('Laser R', GRUOLIN, 37), 'Gruolin RGB Beam (36ch)', 36)
    assert box.text() == 'Remove Laser R?'
    assert box.informativeText() == "It's a Gruolin RGB Beam (36ch) at channels 37–72."
    cancel = box.button(QMessageBox.Cancel)
    assert remove.text() == 'Remove' and box.buttonRole(remove) == QMessageBox.DestructiveRole
    assert box.defaultButton() is cancel and box.escapeButton() is cancel


def test_remove_question_for_a_missing_type(qapp):
    box, _remove = remove_box(None, PatchEntry('Old', 'gone/laser', 10), None, None)
    assert box.informativeText() == 'Its type "gone/laser" isn\'t available.'


# ── Problems ─────────────────────────────────────────────────────────────

def test_problems_show_under_their_rows(fl):
    fl.set_patch(patch(('A', GRUOLIN, 1), ('B', GRUOLIN, 30), ('C', SMALL, 100)),
                 [PatchProblem('B', 'channels 30–65 overlap A (1–36)')])
    assert fl.problem_texts() == [None, 'channels 30–65 overlap A (1–36)', None]
    fl.set_patch(patch(('A', GRUOLIN, 1)))
    assert fl.problem_texts() == [None]


def test_file_problems(fl):
    lines = [f'bindings/acme/x{i}.json: mappings[0]: broken' for i in range(FILE_LINES + 2)]
    fl.set_file_problems(lines)
    assert fl.file_problem_texts() == [*lines[:FILE_LINES], '… and 2 more (see the console)']
    fl.set_file_problems(lines[:1])
    assert fl.file_problem_texts() == lines[:1]
    fl.set_file_problems([])
    assert fl.file_problem_texts() == []


def test_a_long_problem_ends_in_an_ellipsis(fl):
    text = 'bindings/acme/x.json: ' + 'a very long reason, ' * 20
    narrowest = fl.minimumSizeHint().width()
    fl.set_file_problems([text])
    assert fl.minimumSizeHint().width() == narrowest                       # a long text doesn't widen the list
    fl.setFixedWidth(400)
    fl.show()
    label = fl._file_lines[0].label
    assert label.text() == text and label.toolTip() == text
    assert label.shown_text().endswith('…') and len(label.shown_text()) < len(text)


# ── Signals for the panel ────────────────────────────────────────────────

def test_open_folder(fl):
    asked = capture(fl.open_folder_requested)
    fl._open_btn.click()
    assert asked == [None]


def test_size_changed_only_when_the_shape_changes(fl):
    changes = capture(fl.size_changed)
    fl.set_patch(two_gruolins())
    fl.set_patch(two_gruolins())
    assert len(changes) == 1
    fl.set_patch(two_gruolins(), [PatchProblem('Laser R', 'x')])
    fl.set_file_problems(['y'])
    fl.set_patch(Patch())
    assert len(changes) == 4


def test_many_fixtures_scroll(fl):
    fl.set_patch(patch(*((f'L{i}', SMALL, 1 + 4 * i) for i in range(VISIBLE_ROWS))))
    five = fl._scroll.height()
    fl.set_patch(patch(*((f'L{i}', SMALL, 1 + 4 * i) for i in range(VISIBLE_ROWS + 3))))
    assert fl._scroll.height() == five
    assert fl._header.contentsMargins().right() > 0                         # titles stay over their columns
    fl.set_patch(patch(('A', SMALL, 1)))
    assert fl._scroll.height() < five and fl._header.contentsMargins().right() == 0
