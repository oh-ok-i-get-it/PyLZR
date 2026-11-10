"""The app-wide look (gui/style.py): bundled fonts, palette, stylesheet and
plot colours. apply() changes the shared QApplication, so the fixture puts
everything back afterwards and other tests keep running unstyled."""

import pyqtgraph as pg
import pytest
from PyQt5.QtGui import QColor, QFontDatabase, QPalette

from pylzr.gui import style, theme


@pytest.fixture
def styled_app(qapp):
    saved = (qapp.style().objectName(), qapp.palette(), qapp.font(), qapp.styleSheet(),
             pg.getConfigOption('background'), pg.getConfigOption('foreground'))
    style.apply(qapp)
    yield qapp
    name, palette, font, sheet, background, foreground = saved
    qapp.setStyleSheet(sheet)
    qapp.setStyle(name)
    qapp.setPalette(palette)
    qapp.setFont(font)
    pg.setConfigOptions(background=background, foreground=foreground)


def test_bundled_fonts_load(qapp):
    assert {theme.UI_FONT, theme.MONO_FONT} <= style.load_fonts()
    db = QFontDatabase()
    assert {'Regular', 'Medium', 'SemiBold'} <= set(db.styles(theme.UI_FONT))
    assert {'Regular', 'Bold'} <= set(db.styles(theme.MONO_FONT))


def test_every_font_ships_with_its_licence():
    fonts = {path.stem.split('-')[0] for path in style.FONTS.glob('*.ttf')}
    licences = {path.stem.removesuffix('-OFL') for path in style.FONTS.glob('*-OFL.txt')}
    assert fonts and fonts == licences


def test_apply_gives_black_window_fusion_and_inter(styled_app):
    sheet = styled_app.styleSheet()
    styled_app.setStyleSheet('')        # a stylesheet hides the base style behind an unnamed proxy
    assert styled_app.style().objectName() == 'fusion'
    styled_app.setStyleSheet(sheet)
    assert styled_app.palette().color(QPalette.Window) == QColor(theme.BG)
    assert styled_app.palette().color(QPalette.WindowText) == QColor(theme.TEXT)
    assert styled_app.font().family() == theme.UI_FONT
    assert styled_app.font().pixelSize() == theme.SIZE_BODY
    assert styled_app.styleSheet() == style.stylesheet()


def test_plot_colours_set_before_plots_are_built(styled_app):
    assert pg.getConfigOption('background') == theme.BG
    assert pg.getConfigOption('foreground') == theme.AXIS


def test_stylesheet_is_built_from_theme_tokens():
    sheet = style.stylesheet()
    for token in (theme.CARD, theme.RAISED, theme.BUTTON, theme.BORDER, theme.BORDER_STRONG,
                  theme.GROOVE, theme.TEXT, theme.ACCENT, theme.MONO_FONT):   # UI_FONT is set by app.setFont()
        assert token in sheet, token
    for widget in ('QGroupBox', 'QPushButton', 'QSlider', 'QComboBox', 'QLineEdit', 'QSpinBox',
                   'QTextEdit', 'QScrollBar', 'QMenu', 'QToolTip'):
        assert widget + ' ' in sheet or widget + ':' in sheet or widget + ',' in sheet, widget


def test_rgba():
    assert style.rgba('#58a6ff', 0.2) == 'rgba(88, 166, 255, 0.2)'


def test_main_window_builds_and_works_styled(styled_app, make_window):
    """The look changes nothing about behaviour: the window builds, and the
    Sound Mode button and status line still do what they did."""
    harness = make_window()
    controls = harness.window.controls
    assert controls._sm_button.text() == 'Sound Mode: OFF'
    controls._sm_button.click()
    assert controls._sm_button.text() == 'Sound Mode: ON'
    assert controls.status_label.text() == 'Press any key'
