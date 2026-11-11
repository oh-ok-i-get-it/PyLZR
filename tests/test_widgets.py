"""The reusable GUI building blocks (gui/widgets.py)."""

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QHBoxLayout, QLabel

from pylzr.gui import panel_style, style, theme
from pylzr.gui.widgets import Card, IndicatorTile, PlainTextLabel, SectionTitle, ValueLabel


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
    for role in ('section', 'card', 'tile', 'value', 'status', 'sound-mode', 'toolbar-button'):
        assert f'[role="{role}"]' in rules, role
    assert rules in style.stylesheet()
