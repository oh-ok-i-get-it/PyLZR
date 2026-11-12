"""Small helpers shared by the settings panel and its sections
(gui/settings_panel.py, gui/dmx_settings.py), so every section looks alike.
The looks themselves are style roles in gui/style.py."""

from PyQt5.QtWidgets import QLabel, QWidget

from .widgets import SectionTitle, set_role


def label(text: str) -> QLabel:
    """A dim control label, e.g. 'Input Gain'."""
    lbl = QLabel(text)
    set_role(lbl, 'label')
    return lbl


def section(text: str) -> QLabel:
    """A section title, e.g. 'AUDIO' (letter-spaced; see widgets.SectionTitle)."""
    return SectionTitle(text)


def pad(layout, t=8, r=12, b=8, l=12) -> QWidget:  # noqa: E741 — top/right/bottom/left
    """Wrap a layout in a plain (transparent) widget with padding."""
    w = QWidget()
    layout.setContentsMargins(l, t, r, b)
    w.setLayout(layout)
    return w
