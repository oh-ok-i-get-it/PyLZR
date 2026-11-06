"""Styles and small helpers shared by the settings panel and its sections
(gui/settings_panel.py, gui/dmx_settings.py), so every section looks alike."""

from PyQt5.QtWidgets import QLabel, QWidget

from . import theme

SECTION_STYLE = f'color: {theme.ACCENT}; font-size: 9px; font-weight: bold; letter-spacing: 0.08em;'
LABEL_STYLE   = 'color: #666666; font-size: 10px;'

INPUT_STYLE = (
    'QLineEdit, QSpinBox {'
    '  background: #1a1a1a; color: #c9d1d9;'
    '  border: 1px solid #2e2e2e; border-radius: 3px;'
    '  padding: 2px 5px; font-size: 10px;'
    '}'
    f'QLineEdit:hover, QSpinBox:hover, QLineEdit:focus, QSpinBox:focus {{ border-color: {theme.ACCENT}; }}'
)

SMALL_BUTTON_STYLE = (
    'QPushButton {'
    '  background:#1e1e1e; color:#666; font-size:10px;'
    '  border:1px solid #2e2e2e; border-radius:3px; padding:3px 10px;'
    '}'
    f'QPushButton:checked {{ background:#0f3d1a; color:{theme.OK}; border-color:{theme.OK}; }}'
    f'QPushButton:hover   {{ border-color:{theme.ACCENT}; }}'
    'QPushButton:disabled { color:#3a3a3a; border-color:#222222; }'
)


def label(text: str, style: str = LABEL_STYLE) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(style)
    return lbl


def section(text: str) -> QLabel:
    """A section title, e.g. 'AUDIO'."""
    return label(text, SECTION_STYLE)


def pad(layout, t=8, r=12, b=8, l=12) -> QWidget:  # noqa: E741 — top/right/bottom/left
    """Wrap a layout in a transparent widget with padding."""
    w = QWidget()
    w.setStyleSheet('background:transparent;')
    layout.setContentsMargins(l, t, r, b)
    w.setLayout(layout)
    return w
