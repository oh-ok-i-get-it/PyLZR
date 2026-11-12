"""The app-wide look (gui/style.py): bundled fonts, palette, stylesheet and
plot colours. apply() changes the shared QApplication, so the fixture puts
everything back afterwards and other tests keep running unstyled."""

import pyqtgraph as pg
import pytest
from PyQt5.QtCore import Qt
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
    for widget in ('QPushButton', 'QSlider', 'QComboBox', 'QLineEdit', 'QSpinBox',
                   'QTextEdit', 'QScrollBar', 'QMenu', 'QToolTip'):
        assert widget + ' ' in sheet or widget + ':' in sheet or widget + ',' in sheet, widget


def test_rgba():
    assert style.rgba('#58a6ff', 0.2) == 'rgba(88, 166, 255, 0.2)'


def test_mix():
    assert style.mix('#ffffff', '#000000', 0.5) == '#808080'
    assert style.mix('#2ecc71', '#000000', 0) == '#000000'
    assert style.mix('#2ecc71', '#000000', 1) == '#2ecc71'


def test_icons_draw_in_theme_colours(qapp):
    gear = style.icon('settings', theme.TEXT_DIM, on_color=theme.ACCENT)
    assert not gear.isNull()
    assert style.icon('no-such-icon', theme.TEXT).isNull()      # callers keep their text then
    assert not style.status_dot_icon(theme.DISABLED, theme.OK).isNull()


def test_dropdown_arrow_matches_the_theme():
    """Stylesheet images can't be recoloured, so the arrow's colour is in the file."""
    assert f'stroke="{theme.TEXT_DIM}"' in style.COMBO_ARROW.read_text(encoding='utf-8')
    assert style.COMBO_ARROW.as_posix() in style.stylesheet()


def test_every_icon_set_ships_with_its_licence():
    assert list(style.ICONS.glob('*.svg'))
    assert (style.ICONS / 'Lucide-LICENSE.txt').is_file()


def test_placeholder_app_icon_is_set(styled_app):
    assert (style.ICONS / 'app-icon.svg').is_file()
    assert not style.app_icon().isNull()
    assert not styled_app.windowIcon().isNull()


def test_dark_title_bar_does_nothing_offscreen(qapp):
    from PyQt5.QtWidgets import QWidget
    window, child = QWidget(), QWidget()
    child.setParent(window)
    assert style.dark_title_bar(window) is False      # the tests run offscreen
    assert style.dark_title_bar(child) is False       # never on a non-window widget
    assert not child.testAttribute(Qt.WA_NativeWindow)


def test_window_title_is_the_app_name(make_window):
    assert make_window().window.windowTitle() == 'PyLZR'


def test_control_panel_gear_is_an_icon(qapp):
    from pylzr.gui.control_panel import ControlPanel
    panel = ControlPanel()
    assert not panel.gear_button.icon().isNull()
    assert panel.gear_button.size().width() == 30 and panel.gear_button.isCheckable()


def test_main_window_builds_and_works_styled(styled_app, make_window):
    """The look changes nothing about behaviour: the window builds, and the
    Sound Mode button and status line still do what they did."""
    harness = make_window()
    controls = harness.window.controls
    assert controls._sm_button.text() == 'Sound Mode: OFF'
    controls._sm_button.click()
    assert controls._sm_button.text() == 'Sound Mode: ON'
    assert controls.status_label.text() == 'Press any key'


def test_colours_live_in_theme():
    """Hex colours are defined once, in gui/theme.py; other GUI modules use its tokens."""
    import re
    from pathlib import Path

    import pylzr.gui
    hex_colour = re.compile(r'#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3}')
    gui = Path(pylzr.gui.__file__).parent
    found = {f'{path.name}: {match}'
             for path in gui.glob('*.py') if path.name != 'theme.py'
             for match in hex_colour.findall(path.read_text(encoding='utf-8'))}
    assert found == set()
