"""The FIXTURES list in the real settings panel with PyLZR's own fonts and
stylesheet: long names and types fit the 560 px panel, '512' fits the
address box, and many fixtures scroll instead of growing the panel past the
window."""

from PyQt5.QtWidgets import QApplication

from pylzr.core import WINDOW_H
from pylzr.fixtures import Patch, PatchEntry, PatchProblem
from pylzr.gui import SettingsPanel

GRUOLIN = 'gruolin/rgb-beam-36ch'
TYPES   = [(GRUOLIN, 'Gruolin RGB Beam (36ch)', 36)]


def shown_panel(patch, problems=()):
    panel = SettingsPanel()
    fl = panel.dmx.fixtures
    fl.set_types(TYPES)
    fl.set_patch(patch, problems)
    panel.show()
    panel.adjustSize()
    QApplication.processEvents()                               # let the layouts settle
    return panel, fl


def test_rows_fit_the_panel(styled_app):
    long_name = 'Left Truss Laser Downstage No 1'.ljust(32, 'x')
    panel, fl = shown_panel(Patch((PatchEntry(long_name, GRUOLIN, 1), PatchEntry('Laser R', GRUOLIN, 477))),
                            [PatchProblem('Laser R', 'channels 477–512 overlap a fixture with a long name (1–36)')])
    assert panel.width() == 560
    for row in fl._rows:
        right = row.remove.mapTo(panel, row.remove.rect().topRight()).x()
        assert right < panel.width() - 8                       # inside the panel's padding
        assert row.name.width() >= 120                         # room for a name
    combo = fl._rows[1].type
    assert combo.shown_text() == 'Gruolin RGB Beam (36ch)'     # the type name isn't cut
    box = fl._rows[1].address
    assert box.fontMetrics().horizontalAdvance('512') < box.contentsRect().width() - 6
    panel.close()


def test_column_titles_sit_over_their_columns(styled_app):
    panel, fl = shown_panel(Patch((PatchEntry('A', GRUOLIN, 1),)))
    header = fl._header
    type_title = header.itemAt(1).widget()
    combo = fl._rows[0].type
    x = lambda w: w.mapTo(panel, w.rect().topLeft()).x()       # noqa: E731
    assert x(type_title) == x(combo)
    panel.close()


def test_many_fixtures_scroll_instead_of_growing_past_the_window(styled_app):
    many = Patch(tuple(PatchEntry(f'Laser {i + 1}', GRUOLIN, 1 + 36 * i) for i in range(12)))
    panel, fl = shown_panel(many)
    assert fl._scroll.verticalScrollBar().isVisible()
    assert panel.height() < WINDOW_H - 120                     # it hangs below the toolbar, inside the window
    type_title = fl._header.itemAt(1).widget()
    x = lambda w: w.mapTo(panel, w.rect().topLeft()).x()       # noqa: E731
    assert x(type_title) == x(fl._rows[0].type)                # still lined up with the scroll bar showing
    panel.close()


def below(panel, upper, lower):
    """True if `lower` starts at or below the bottom of `upper` (in panel coordinates)."""
    return lower.mapTo(panel, lower.rect().topLeft()).y() >= upper.mapTo(panel, upper.rect().bottomLeft()).y()


def test_the_panel_grows_and_shrinks_with_the_list(styled_app):
    panel, fl = shown_panel(Patch((PatchEntry('A', GRUOLIN, 1),)))
    small = panel.height()
    fl.set_patch(Patch(tuple(PatchEntry(f'Laser {i + 1}', GRUOLIN, 1 + 36 * i) for i in range(8))))
    fl.set_file_problems(['bindings/acme/x.json: broken'])
    assert panel.height() > small and panel.height() >= panel.sizeHint().height()   # straight away
    QApplication.processEvents()
    assert below(panel, fl._scroll, fl._add_btn)                                    # nothing overlaps
    assert below(panel, fl._add_btn, fl._file_lines[0])
    old_line = fl._file_lines[0]
    fl.set_patch(Patch((PatchEntry('A', GRUOLIN, 1),)))
    fl.set_file_problems([])
    assert panel.height() == small
    assert fl.file_problem_texts() == [] and not old_line.isVisible()        # gone at once, not on deletion
    panel.close()


def test_names_use_the_ui_font_and_numbers_stay_mono(styled_app):
    from pylzr.gui import theme
    panel, fl = shown_panel(Patch((PatchEntry('A', GRUOLIN, 1),)))
    assert fl._rows[0].name.font().family() == theme.UI_FONT
    assert fl._rows[0].address.font().family() == theme.MONO_FONT
    assert panel.dmx._node_ip_edit.font().family() == theme.MONO_FONT
    panel.close()
