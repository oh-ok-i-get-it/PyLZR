"""The reusable GUI building blocks (gui/widgets.py)."""

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QHBoxLayout, QLabel

from pylzr.gui import panel_style, style, theme
from pylzr.gui.widgets import (
    Card, ElidedComboBox, ElidedLabel, IndicatorTile, PlainTextLabel, ProblemLine, SectionTitle, ValueLabel,
    set_props,
)


def shown(label: QLabel) -> str:
    """What the label really displays (QLabel's own text, i.e. the rich text)."""
    return QLabel.text(label)


def test_plain_text_label_keeps_what_it_was_given(qapp):
    label = PlainTextLabel('a\nb')
    assert label.text() == 'a\nb'
    label.setText('c')
    assert label.text() == 'c' and shown(label) == 'c'


def test_text_is_escaped(qapp):
    label = ValueLabel('<b>Name</b>: 1 & 2')
    assert label.text() == '<b>Name</b>: 1 & 2'
    assert '&lt;b&gt;Name&lt;/b&gt;:' in shown(label) and '1 &amp; 2' in shown(label)


def test_indicator_tile_shows_label_over_value_in_its_tone(qapp):
    tile = IndicatorTile('LOW\n2', tone='low', value_size=20)
    assert tile.text() == 'LOW\n2'
    html = shown(tile)
    assert html.index('LOW') < html.index('<br>') < html.index('>2<')
    assert theme.LOW_BAND in html and 'font-size:20px' in html and theme.MONO_FONT in html
    tile.setText('LOW\n—')
    assert tile.text() == 'LOW\n—'
    assert tile.property('role') == 'tile' and tile.property('tone') == 'low'


def test_value_label_dims_the_name_and_brightens_the_value(qapp):
    label = ValueLabel('Quiet: 1200')
    html = shown(label)
    assert label.text() == 'Quiet: 1200'
    assert html.index('Quiet:') < html.index('1200')
    assert theme.TEXT_DIM in html and theme.TEXT in html and theme.MONO_FONT in html
    readout = ValueLabel('100%')                     # no name: all value
    assert readout.text() == '100%' and theme.TEXT_DIM not in shown(readout)


def test_section_title_is_letter_spaced(qapp):
    title = SectionTitle('AUDIO')
    assert title.font().letterSpacing() == theme.TRACKING
    assert title.font().letterSpacingType() == QFont.PercentageSpacing
    assert title.property('role') == 'section' and title.property('tone') == 'accent'
    assert SectionTitle('CONSOLE', tone='dim').property('tone') == 'dim'
    assert isinstance(panel_style.section('APP'), SectionTitle)


def test_card_puts_content_in_its_body(qapp):
    card = Card('LOW CUTOFFS')
    content = QLabel('x')
    card.addWidget(content)
    assert card.title.text() == 'LOW CUTOFFS'
    assert card.body.indexOf(content) == 0
    assert card.property('role') == 'card'

    row = Card(body=QHBoxLayout())                   # untitled, horizontal body
    assert row.title is None and isinstance(row.body, QHBoxLayout)


def test_every_role_has_rules():
    rules = style.role_rules()
    for role in ('section', 'card', 'tile', 'value', 'status', 'sound-mode', 'toolbar-button', 'log', 'label',
                 'detail', 'readout', 'input', 'small-button', 'popover', 'divider', 'meter', 'clip',
                 'warning', 'problem', 'plain-scroll'):
        assert f'[role="{role}"]' in rules, role
    assert rules in style.stylesheet()


def test_set_props_changes_only_what_differs(qapp):
    label = QLabel()
    set_props(label, state='off')
    assert label.property('state') == 'off'
    set_props(label, state='on')
    assert label.property('state') == 'on'
    assert panel_style.label('Gain').property('role') == 'label'


def test_elided_combo_shortens_only_what_does_not_fit(qapp):
    from PyQt5.QtCore import Qt
    combo = ElidedComboBox()
    combo.addItem('Focusrite USB Audio (Scarlett 2i2 4th Gen)')
    combo.setItemData(0, 'Focusrite USB Audio (Scarlett 2i2 4th Gen) — full', Qt.ToolTipRole)
    combo.addItem('Mic')
    combo.setFixedWidth(150)
    combo.show()
    assert combo.shown_text().endswith('…') and len(combo.shown_text()) < len(combo.currentText())
    assert combo.full_text().endswith('— full')                # the tooltip names it in full
    combo.setCurrentIndex(1)
    assert combo.shown_text() == 'Mic' == combo.full_text()   # fits: shown as is
    assert combo.sizeHint().width() < 150                     # a long name doesn't ask for more room


def test_elided_combo_shows_its_placeholder(qapp):
    combo = ElidedComboBox()
    combo.setPlaceholderText('No devices found')
    combo.setFixedWidth(200)
    combo.show()
    assert combo.currentIndex() == -1 and combo.shown_text() == 'No devices found'


def test_elided_label_shortens_only_what_does_not_fit(qapp):
    text = 'bindings/acme/laser.json: mappings[3].segment: no capability of "Colour" covers 300'
    label = ElidedLabel(text)
    label.setFixedWidth(120)
    label.show()
    assert label.text() == text == label.toolTip()
    assert label.shown_text().endswith('…') and len(label.shown_text()) < len(text)
    assert label.minimumSizeHint().width() == 0                # never widens its row
    label.setText('Short')
    assert label.shown_text() == 'Short' == label.text()
    label.setFixedWidth(2000)                                  # given room, the full text comes back
    label.setText(text)
    assert label.shown_text() == text


def test_problem_line_is_an_amber_triangle_and_text(qapp):
    line = ProblemLine('channels 30–65 overlap Laser L (1–36)')
    assert line.text() == 'channels 30–65 overlap Laser L (1–36)'
    assert line.label.property('role') == 'problem'
    assert line.icon.pixmap() is not None and not line.icon.pixmap().isNull()
    line.setText('x')
    assert line.text() == 'x'
