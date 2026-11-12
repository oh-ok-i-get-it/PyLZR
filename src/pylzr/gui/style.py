"""The app-wide look: bundled fonts, the Fusion style, a black palette, one
stylesheet and pyqtgraph's colours, all built from the tokens in theme.py.

apply() runs once in __main__.main(), right after the QApplication exists and
before any window is built. It only changes how widgets look. A widget's own
setStyleSheet() still wins over these rules where both set the same thing.

Style roles (set with widgets.set_role(); rules in role_rules()). Prefer these
building blocks from gui/widgets.py over per-widget stylesheets:
    section         SectionTitle: small-caps title; tone 'accent' (default) or 'dim'
    card            Card: rounded panel on the window background
    tile            IndicatorTile: DM / CNT / LOW / HIGH; tone 'neutral', 'low' or 'high'
    value           ValueLabel: 'Name: value' with a bright mono value
    log             a read-only text box sitting borderless on a card (Console, Averages)
    label           a control label ('Input Gain'); tone 'dim' (default) or 'light'; panel_style.label() makes one
    detail          a short bright text beside a label (a connection's port or device)
    readout         a bright mono value on its own ('100%', '43 fps')
    input           a compact line edit / spin box (11 px mono)
    small-button    a compact 22 px button, green when checked; shape 'icon' for icon-only
    popover         a floating panel: card colour with an accent stripe on top (Settings)
    divider         a 1 px line between sections (a QFrame)
    meter           the signal level bar (a QProgressBar)
    clip            the CLIP badge; state 'on' or 'off' (change it with widgets.set_props)
    warning         an amber strip with a short caution (the DMX tester's live-output warning)
    status          a muted one-line status label
    sound-mode      the big Sound Mode toggle (its dot is the button's on/off icon)
    toolbar-button  an icon-only button, outlined on hover, accent when checked (the gear)
"""

import sys
from pathlib import Path

import pyqtgraph as pg
from PyQt5.QtCore import QByteArray, QPointF, QRectF, Qt
from PyQt5.QtGui import (
    QColor, QFont, QFontDatabase, QGuiApplication, QIcon, QPainter, QPalette, QPixmap, QRadialGradient,
)
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QApplication, QStyleFactory, QWidget

from . import theme

ASSETS = Path(__file__).parent / 'assets'
FONTS  = ASSETS / 'fonts'
ICONS  = ASSETS / 'icons'
COMBO_ARROW = ICONS / 'combo-arrow.svg'   # drawn in theme.TEXT_DIM (stylesheet images can't be recoloured)

# The app icon: the first of these that exists. app-icon.svg is a placeholder;
# drop in the real icon as app-icon.ico / .png (or replace the .svg).
APP_ICON_FILES = ('app-icon.ico', 'app-icon.png', 'app-icon.svg')
_APP_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)

# DwmSetWindowAttribute: DWMWA_USE_IMMERSIVE_DARK_MODE is 20, and was 19
# before Windows 10 20H1
_DARK_MODE_ATTRIBUTES = (20, 19)


def rgba(hex_color: str, alpha: float) -> str:
    """rgba(theme.ACCENT, 0.2) -> 'rgba(88, 166, 255, 0.2)', for tinted fills in stylesheets."""
    c = QColor(hex_color)
    return f'rgba({c.red()}, {c.green()}, {c.blue()}, {alpha})'


def mix(color: str, base: str, amount: float) -> str:
    """`amount` of `color` over `base`, as a hex colour (0 gives base, 1 gives color).
    For tints that must be solid, e.g. a band-coloured border on a dark tile."""
    a, b = QColor(color), QColor(base)
    blend = [round(x * amount + y * (1 - amount)) for x, y in
             ((a.red(), b.red()), (a.green(), b.green()), (a.blue(), b.blue()))]
    return '#{:02x}{:02x}{:02x}'.format(*blend)


# ── Icons ─────────────────────────────────────────────────────────────────────

def _pixmap(size: int) -> QPixmap:
    """Transparent square pixmap, drawn at 2x (or the screen's ratio) so it stays sharp."""
    app = QApplication.instance()
    ratio = max(2.0, app.devicePixelRatio() if app else 1.0)
    pm = QPixmap(round(size * ratio), round(size * ratio))
    pm.setDevicePixelRatio(ratio)
    pm.fill(Qt.transparent)
    return pm


def _render_svg(svg: str, pm: QPixmap, size: int) -> QPixmap:
    """Draw SVG text into `pm` (logical size `size`); null pixmap if it isn't valid SVG."""
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    if not renderer.isValid():
        return QPixmap()
    painter = QPainter(pm)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pm


def _svg_pixmap(name: str, color: str, size: int) -> QPixmap:
    """assets/icons/<name>.svg drawn in `color` (the SVG strokes with currentColor)."""
    path = ICONS / f'{name}.svg'
    if not path.is_file():
        return QPixmap()
    return _render_svg(path.read_text(encoding='utf-8').replace('currentColor', color), _pixmap(size), size)


def app_icon() -> QIcon:
    """The window / taskbar icon from APP_ICON_FILES; null if none can be read."""
    for name in APP_ICON_FILES:
        path = ICONS / name
        if not path.is_file():
            continue
        if path.suffix == '.svg':
            result = QIcon()
            svg = path.read_text(encoding='utf-8')
            for size in _APP_ICON_SIZES:
                pm = QPixmap(size, size)
                pm.fill(Qt.transparent)
                pm = _render_svg(svg, pm, size)
                if not pm.isNull():
                    result.addPixmap(pm)
        else:
            result = QIcon(str(path))
        if not result.isNull():
            return result
    return QIcon()


def dark_title_bar(window: QWidget) -> bool:
    """Ask Windows 10 (20H1 or later) / 11 to draw `window`'s title bar dark.
    Returns whether Windows accepted it. Does nothing, and returns False, on
    other systems, offscreen, for non-window widgets, or if the call fails."""
    if sys.platform != 'win32' or QGuiApplication.platformName() != 'windows' or not window.isWindow():
        return False
    try:
        import ctypes
        hwnd = ctypes.c_void_p(int(window.winId()))
        on = ctypes.c_int(1)
        dwm = ctypes.windll.dwmapi
        return any(dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(on), ctypes.sizeof(on)) == 0
                   for attribute in _DARK_MODE_ATTRIBUTES)
    except (AttributeError, OSError):
        return False


def icon(name: str, color: str, on_color: str | None = None, size: int = 16) -> QIcon:
    """A line icon from assets/icons in theme colours. With `on_color`, a checked
    button shows the icon in that colour instead. Null if the icon can't be
    drawn, so callers can keep their text as a fallback."""
    normal = _svg_pixmap(name, color, size)
    if normal.isNull():
        return QIcon()
    result = QIcon()
    result.addPixmap(normal, QIcon.Normal, QIcon.Off)
    result.addPixmap(_svg_pixmap(name, on_color or color, size), QIcon.Normal, QIcon.On)
    return result


def status_dot_icon(off_color: str, on_color: str, size: int = 16) -> QIcon:
    """A small dot: plain `off_color` when off, `on_color` with a soft halo when on
    (stylesheets can't blur, so the halo lives in the icon)."""
    def draw(color: str, halo: bool) -> QPixmap:
        pm = _pixmap(size)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        centre = QPointF(size / 2, size / 2)
        if halo:
            glow = QRadialGradient(centre, size / 2)
            for stop, alpha in ((0.0, 0.55), (0.55, 0.3), (1.0, 0.0)):
                c = QColor(color)
                c.setAlphaF(alpha)
                glow.setColorAt(stop, c)
            painter.setBrush(glow)
            painter.drawEllipse(centre, size / 2, size / 2)
        painter.setBrush(QColor(color))
        painter.drawEllipse(centre, size * 0.28, size * 0.28)
        painter.end()
        return pm

    result = QIcon()
    result.addPixmap(draw(off_color, False), QIcon.Normal, QIcon.Off)
    result.addPixmap(draw(on_color, True), QIcon.Normal, QIcon.On)
    return result


def text_weight() -> int:
    """theme.WEIGHT_TEXT (CSS scale, 100–900) on Qt 5's QFont scale (0–99)."""
    return {400: QFont.Normal, 500: QFont.Medium, 600: QFont.DemiBold, 700: QFont.Bold}[theme.WEIGHT_TEXT]


def load_fonts() -> set[str]:
    """Register the bundled fonts with Qt and return their family names.
    A font that fails to load is skipped; Qt then falls back to the system font."""
    families = set()
    for path in sorted(FONTS.glob('*.ttf')):
        font_id = QFontDatabase.addApplicationFont(str(path))
        if font_id != -1:
            families.update(QFontDatabase.applicationFontFamilies(font_id))
    return families


def palette() -> QPalette:
    """Black palette for everything the stylesheet doesn't cover (window
    background, plain labels, Fusion's own drawing)."""
    p = QPalette()
    for role, color in (
        (QPalette.Window,          theme.BG),
        (QPalette.WindowText,      theme.TEXT),
        (QPalette.Base,            theme.RAISED),
        (QPalette.AlternateBase,   theme.CARD),
        (QPalette.Text,            theme.TEXT),
        (QPalette.PlaceholderText, theme.TEXT_MUTED),
        (QPalette.Button,          theme.BUTTON),
        (QPalette.ButtonText,      theme.TEXT),
        (QPalette.BrightText,      theme.WHITE),
        (QPalette.ToolTipBase,     theme.RAISED),
        (QPalette.ToolTipText,     theme.TEXT),
        (QPalette.Highlight,       theme.ACCENT),
        (QPalette.HighlightedText, theme.BG),
        (QPalette.Link,            theme.ACCENT),
        (QPalette.Light,           theme.BORDER_STRONG),
        (QPalette.Midlight,        theme.BORDER),
        (QPalette.Mid,             theme.BORDER),
        (QPalette.Dark,            theme.BG),
        (QPalette.Shadow,          theme.BG),
    ):
        p.setColor(role, QColor(color))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        p.setColor(QPalette.Disabled, role, QColor(theme.DISABLED))
    return p


def stylesheet() -> str:
    """App-wide rules, one block per widget type."""
    t = theme
    tint = rgba(t.ACCENT, 0.18)
    ring = rgba(t.ACCENT, 0.35)
    return f'''
QToolTip {{
    background: {t.RAISED}; color: {t.TEXT};
    border: 1px solid {t.BORDER_STRONG}; border-radius: 5px; padding: 4px 8px;
}}

QPushButton {{
    background: {t.BUTTON}; color: {t.TEXT};
    border: 1px solid {t.BORDER_STRONG}; border-radius: {t.RADIUS}px;
    padding: 3px 6px;   /* small enough that a 30x30 glyph button (the gear) isn't clipped */
}}
QPushButton:hover, QPushButton:focus {{ border-color: {t.ACCENT}; }}
QPushButton:pressed {{ background: {t.RAISED}; }}
QPushButton:checked {{ background: {tint}; border-color: {t.ACCENT}; }}
QPushButton:disabled {{ background: {t.CARD}; color: {t.DISABLED}; border-color: {t.BORDER}; }}

QSlider {{ background: transparent; }}
QSlider::groove:horizontal {{ background: {t.GROOVE}; height: 4px; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {t.ACCENT}; height: 4px; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {t.ACCENT}; width: 10px; height: 10px; margin: -5px 0;
    border: 2px solid {t.BG}; border-radius: 7px;
}}
QSlider::groove:vertical {{ background: {t.GROOVE}; width: 4px; border-radius: 2px; }}
QSlider::add-page:vertical {{ background: {t.ACCENT}; width: 4px; border-radius: 2px; }}
QSlider::handle:vertical {{
    background: {t.ACCENT}; width: 10px; height: 10px; margin: 0 -5px;
    border: 2px solid {t.BG}; border-radius: 7px;
}}
QSlider::handle:hover {{ border-color: {ring}; }}
QSlider::sub-page:disabled, QSlider::add-page:vertical:disabled, QSlider::handle:disabled {{
    background: {t.DISABLED};
}}

QLineEdit, QSpinBox, QComboBox {{
    background: {t.RAISED}; color: {t.TEXT};
    border: 1px solid {t.BORDER_STRONG}; border-radius: {t.RADIUS}px; padding: 2px 6px;
    selection-background-color: {t.ACCENT}; selection-color: {t.BG};
}}
QLineEdit, QSpinBox {{ font-family: "{t.MONO_FONT}"; }}
QLineEdit:hover, QSpinBox:hover, QComboBox:hover,
QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {t.ACCENT}; }}
QLineEdit:disabled, QSpinBox:disabled, QComboBox:disabled {{ color: {t.DISABLED}; border-color: {t.BORDER}; }}
QComboBox {{ padding: 3px 22px 3px 8px; }}
QComboBox::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right; width: 20px; border: none;
}}
QComboBox::down-arrow {{ image: url("{COMBO_ARROW.as_posix()}"); width: 12px; height: 12px; }}
QComboBox QAbstractItemView {{
    background: {t.RAISED}; color: {t.TEXT}; border: 1px solid {t.BORDER_STRONG};
    selection-background-color: {tint}; selection-color: {t.TEXT}; outline: 0; padding: 4px;
}}

QTextEdit, QPlainTextEdit {{
    background: {t.CARD}; color: {t.TEXT};
    border: 1px solid {t.BORDER}; border-radius: {t.RADIUS_CARD}px;
    font-family: "{t.MONO_FONT}"; font-size: {t.SIZE_LABEL}px;
    selection-background-color: {t.ACCENT}; selection-color: {t.BG};
}}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
QScrollBar::handle {{ background: {t.SCROLL_HANDLE}; border-radius: 3px; margin: 2px; }}
QScrollBar::handle:hover {{ background: {t.SCROLL_HOVER}; }}
QScrollBar::handle:vertical {{ min-height: 24px; }}
QScrollBar::handle:horizontal {{ min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

QMenu {{
    background: {t.RAISED}; color: {t.TEXT};
    border: 1px solid {t.BORDER_STRONG}; border-radius: {t.RADIUS_CARD}px; padding: 4px;
}}
QMenu::item {{ padding: 5px 12px; border-radius: 5px; }}
QMenu::item:selected {{ background: {tint}; }}
QMenu::item:disabled {{ color: {t.TEXT_MUTED}; }}

QTabWidget::pane {{ border: none; border-top: 1px solid {t.DIVIDER}; }}
QTabBar {{ background: transparent; qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent; color: {t.TEXT_DIM}; font-size: {t.SIZE_LABEL}px; font-weight: 600;
    border: none; border-bottom: 2px solid transparent; padding: 4px 12px 6px 12px; margin-right: 4px;
}}
QTabBar::tab:hover {{ color: {t.TEXT}; }}
QTabBar::tab:selected {{ color: {t.TEXT}; border-bottom-color: {t.ACCENT}; }}

QMessageBox QLabel#qt_msgbox_label, QMessageBox QLabel#qt_msgbox_informativelabel {{ min-width: 260px; }}
{role_rules()}'''


def role_rules() -> str:
    """Rules for the style roles set by gui/widgets.py (setProperty('role', ...)).
    Fonts that need letter spacing are set on the widget instead (see widgets.title_font)."""
    t = theme
    return f'''
QLabel[role="section"] {{ color: {t.ACCENT}; background: transparent; }}
QLabel[role="section"][tone="dim"] {{ color: {t.TEXT_DIM}; }}

QFrame[role="card"] {{
    background: {t.CARD}; border: 1px solid {t.BORDER}; border-radius: {t.RADIUS_CARD}px;
}}

QLabel[role="tile"] {{
    background: {t.CARD}; border: 1px solid {t.TILE_BORDER}; border-radius: {t.RADIUS_CARD}px;
}}
QLabel[role="tile"][tone="low"]  {{ border-color: {mix(t.LOW_BAND, t.TILE_BORDER, 0.35)}; }}
QLabel[role="tile"][tone="high"] {{ border-color: {mix(t.HIGH_BAND, t.TILE_BORDER, 0.35)}; }}

QLabel[role="value"] {{ background: transparent; }}
QTextEdit[role="log"] {{ background: transparent; border: none; }}

QLabel[role="label"]   {{ color: {t.TEXT_DIM}; font-size: {t.SIZE_LABEL}px; background: transparent; }}
QLabel[role="label"][tone="light"] {{ color: {t.TEXT}; }}
QLabel[role="warning"] {{
    color: {t.WARN}; background: {mix(t.WARN, t.BG, 0.07)}; border: 1px solid {mix(t.WARN, t.BG, 0.25)};
    border-radius: {t.RADIUS}px; padding: 5px 10px; font-size: {t.SIZE_LABEL}px;
}}
QLabel[role="detail"]  {{ color: {t.TEXT}; font-size: {t.SIZE_LABEL}px; background: transparent; }}
QLabel[role="problem"] {{ color: {t.WARN}; font-size: {t.SIZE_LABEL}px; background: transparent; }}
QLabel[role="readout"] {{
    color: {t.TEXT}; font-family: "{t.MONO_FONT}"; font-size: {t.SIZE_LABEL}px; background: transparent;
}}

QLineEdit[role="input"], QSpinBox[role="input"] {{ padding: 2px 5px; font-size: {t.SIZE_LABEL}px; }}
QLineEdit[role="input"][kind="text"] {{ font-family: "{t.UI_FONT}"; }}

QPushButton[role="small-button"] {{ font-size: {t.SIZE_LABEL}px; padding: 3px 10px; }}
QPushButton[role="small-button"][shape="icon"] {{ padding: 0; }}
QPushButton[role="small-button"]:focus {{ border-color: {t.BORDER_STRONG}; }}
QPushButton[role="small-button"]:hover {{ border-color: {t.ACCENT}; }}
QPushButton[role="small-button"]:checked {{ background: {t.OK_TINT}; color: {t.OK}; border-color: {t.OK}; }}
QPushButton[role="small-button"]:disabled {{ background: {t.CARD}; color: {t.DISABLED}; border-color: {t.BORDER}; }}

QWidget[role="popover"] {{
    background: {t.CARD}; border: 1px solid {t.BORDER_STRONG}; border-top: 2px solid {t.ACCENT};
    border-radius: {t.RADIUS_CARD}px;
}}
QFrame[role="divider"] {{ background: {t.DIVIDER}; border: none; }}
QScrollArea[role="plain-scroll"] {{ background: transparent; border: none; }}
QScrollArea[role="plain-scroll"] > QWidget > QWidget {{ background: transparent; }}

QProgressBar[role="meter"] {{
    background: {t.RAISED}; border: 1px solid {t.BORDER_STRONG}; border-radius: 4px; text-align: center;
}}
QProgressBar[role="meter"]::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {t.OK}, stop:0.6 {t.METER_MID}, stop:1 {t.ERROR});
    border-radius: 2px;
}}

QLabel[role="clip"] {{
    border-radius: 3px; font-family: "{t.MONO_FONT}"; font-size: 8px; font-weight: bold; padding: 1px 3px;
    background: {t.RAISED}; color: {t.DISABLED};
}}
QLabel[role="clip"][state="on"] {{ background: {t.ERROR}; color: {t.WHITE}; }}
QLabel[role="status"] {{ color: {t.TEXT_MUTED}; font-size: {t.SIZE_LABEL}px; }}

QPushButton[role="sound-mode"] {{
    background: {t.CARD}; color: {t.TEXT_DIM};
    border: 1px solid {t.BORDER_STRONG}; border-radius: {t.RADIUS_CARD}px;
    font-size: {t.SIZE_TITLE}px; font-weight: 600; padding: 0 12px;
}}
QPushButton[role="sound-mode"]:hover {{ border-color: {t.HOVER_EDGE}; }}
QPushButton[role="sound-mode"]:checked {{
    background: {mix(t.OK, t.BG, 0.09)}; color: {mix(t.OK, t.WHITE, 0.5)};
    border-color: {mix(t.OK, t.BG, 0.55)};
}}
QPushButton[role="sound-mode"]:checked:hover {{ border-color: {t.OK}; }}

QPushButton[role="toolbar-button"] {{
    background: transparent; color: {t.TEXT_DIM}; font-size: 17px;
    border: 1px solid transparent; border-radius: {t.RADIUS}px; padding: 0;
}}
QPushButton[role="toolbar-button"]:hover {{ background: {t.BUTTON}; border-color: {t.BORDER_STRONG}; }}
QPushButton[role="toolbar-button"]:checked {{
    background: {mix(t.ACCENT, t.BG, 0.14)}; border-color: {t.ACCENT}; color: {t.ACCENT};
}}
'''


def apply(app: QApplication) -> None:
    """Give the whole app the black look. Call before building any window:
    pyqtgraph reads its colours when a plot is created."""
    families = load_fonts()
    app.setStyle(QStyleFactory.create('Fusion'))
    app.setPalette(palette())
    if theme.UI_FONT in families:
        font = QFont(theme.UI_FONT)
        font.setPixelSize(theme.SIZE_BODY)
        font.setWeight(text_weight())       # rules that set only size or family keep this weight
        app.setFont(font)
    app.setStyleSheet(stylesheet())
    pg.setConfigOptions(background=theme.BG, foreground=theme.AXIS)
    window_icon = app_icon()
    if not window_icon.isNull():
        app.setWindowIcon(window_icon)
