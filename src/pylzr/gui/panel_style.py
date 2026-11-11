"""Styles and small helpers shared by the settings panel and its sections
(gui/settings_panel.py, gui/dmx_settings.py), so every section looks alike."""

from PyQt5.QtWidgets import QLabel, QWidget

from . import theme
from .widgets import SectionTitle

LABEL_STYLE   = f'color: {theme.TEXT_DIM}; font-size: {theme.SIZE_LABEL}px; background: transparent;'

INPUT_STYLE = (
    'QLineEdit, QSpinBox {'
    f'  background: {theme.RAISED}; color: {theme.TEXT};'
    f'  border: 1px solid {theme.BORDER_STRONG}; border-radius: {theme.RADIUS}px;'
    f'  padding: 2px 5px; font-family: "{theme.MONO_FONT}"; font-size: {theme.SIZE_LABEL}px;'
    '}'
    f'QLineEdit:hover, QSpinBox:hover, QLineEdit:focus, QSpinBox:focus {{ border-color: {theme.ACCENT}; }}'
)

_SMALL_BUTTON_BASE = (
    'QPushButton {{'
    f'  background: {theme.BUTTON}; color: {theme.TEXT}; font-size: {theme.SIZE_LABEL}px;'
    f'  border: 1px solid {theme.BORDER_STRONG}; border-radius: {theme.RADIUS}px; padding: {{padding}};'
    '}}'
    f'QPushButton:hover    {{{{ border-color: {theme.ACCENT}; }}}}'
    f'QPushButton:pressed  {{{{ background: {theme.RAISED}; }}}}'
    f'QPushButton:checked  {{{{ background: {theme.OK_TINT}; color: {theme.OK}; border-color: {theme.OK}; }}}}'
    f'QPushButton:disabled {{{{ background: {theme.CARD}; color: {theme.DISABLED}; border-color: {theme.BORDER}; }}}}'
)
SMALL_BUTTON_STYLE = _SMALL_BUTTON_BASE.format(padding='3px 10px')
ICON_BUTTON_STYLE  = _SMALL_BUTTON_BASE.format(padding='0')   # small square buttons showing just an icon


def label(text: str, style: str = LABEL_STYLE) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(style)
    return lbl


def section(text: str) -> QLabel:
    """A section title, e.g. 'AUDIO' (letter-spaced; see widgets.SectionTitle)."""
    return SectionTitle(text)


def pad(layout, t=8, r=12, b=8, l=12) -> QWidget:  # noqa: E741 — top/right/bottom/left
    """Wrap a layout in a transparent widget with padding."""
    w = QWidget()
    w.setStyleSheet('background:transparent;')
    layout.setContentsMargins(l, t, r, b)
    w.setLayout(layout)
    return w
