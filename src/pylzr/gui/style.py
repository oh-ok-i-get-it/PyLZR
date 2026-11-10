"""The app-wide look: bundled fonts, the Fusion style, a black palette, one
stylesheet and pyqtgraph's colours, all built from the tokens in theme.py.

apply() runs once in __main__.main(), right after the QApplication exists and
before any window is built. It only changes how widgets look. A widget's own
setStyleSheet() still wins over these rules where both set the same thing.
"""

from pathlib import Path

import pyqtgraph as pg
from PyQt5.QtCore import QByteArray, QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPalette, QPixmap, QRadialGradient
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QApplication, QStyleFactory

from . import theme

ASSETS = Path(__file__).parent / 'assets'
FONTS  = ASSETS / 'fonts'
ICONS  = ASSETS / 'icons'
COMBO_ARROW = ICONS / 'combo-arrow.svg'   # drawn in theme.TEXT_DIM (stylesheet images can't be recoloured)


def rgba(hex_color: str, alpha: float) -> str:
    """'#58a6ff', 0.2 -> 'rgba(88, 166, 255, 0.2)' for tinted fills in stylesheets."""
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


def _svg_pixmap(name: str, color: str, size: int) -> QPixmap:
    """assets/icons/<name>.svg drawn in `color` (the SVG strokes with currentColor)."""
    path = ICONS / f'{name}.svg'
    if not path.is_file():
        return QPixmap()
    renderer = QSvgRenderer(QByteArray(path.read_text(encoding='utf-8').replace('currentColor', color).encode()))
    if not renderer.isValid():
        return QPixmap()
    pm = _pixmap(size)
    painter = QPainter(pm)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pm


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
        (QPalette.BrightText,      '#ffffff'),
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

QGroupBox {{
    background: {t.CARD}; border: 1px solid {t.BORDER}; border-radius: {t.RADIUS_CARD}px;
    margin-top: 0px; padding: 22px 10px 6px 10px;
    font-size: {t.SIZE_SECTION}px; font-weight: 600;   /* the title's font; Qt ignores fonts on ::title */
}}
QGroupBox::title {{
    subcontrol-origin: padding; subcontrol-position: top left;
    left: 12px; top: 9px; color: {t.ACCENT};
}}
QGroupBox QLabel {{ font-size: {t.SIZE_BODY}px; font-weight: normal; }}

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
QScrollBar::handle {{ background: #333333; border-radius: 3px; margin: 2px; }}
QScrollBar::handle:hover {{ background: #444444; }}
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
        app.setFont(font)
    app.setStyleSheet(stylesheet())
    pg.setConfigOptions(background=theme.BG, foreground=theme.AXIS)
