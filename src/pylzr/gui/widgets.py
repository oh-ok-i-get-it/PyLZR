"""Small reusable building blocks for the GUI.

Each one marks itself with a style role (setProperty('role', ...)); the look
for every role lives in one place, gui/style.py. What stylesheets can't
express is set here: letter spacing (on the font) and two-part text (as rich
text inside a label).

- SectionTitle    small-caps, letter-spaced title ('LOW CUTOFFS')
- Card            rounded panel with an optional SectionTitle and a body layout
- PlainTextLabel  shows formatted text but text() returns the plain text it was given
- IndicatorTile   'LOW\\n2' as a small label over a big number
- ValueLabel      'Quiet: 1200' as a dim name and a bright mono value
"""

import html

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QBoxLayout, QFrame, QLabel, QLayout, QVBoxLayout, QWidget

from . import theme

# Indicator tile tones: the colour of the number (the edge tint is in gui/style.py)
TILE_TONES = {'neutral': theme.TEXT_DIM, 'low': theme.LOW_BAND, 'high': theme.HIGH_BAND}


def set_role(widget: QWidget, role: str, **props: str) -> None:
    """Mark `widget` for a style role in gui/style.py, plus optional extra
    properties the rules can match on (e.g. tone='dim')."""
    widget.setProperty('role', role)
    for name, value in props.items():
        widget.setProperty(name, value)


def set_props(widget: QWidget, **props: str) -> None:
    """Change style properties of a shown widget (e.g. state='on') and
    re-apply its rules. Does nothing when the values are unchanged, so it is
    cheap to call on every update."""
    changed = False
    for name, value in props.items():
        if widget.property(name) != value:
            widget.setProperty(name, value)
            changed = True
    if changed:
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def title_font() -> QFont:
    """Font of small-caps titles: semibold, letter-spaced."""
    font = QFont(theme.UI_FONT)
    font.setPixelSize(theme.SIZE_SECTION)
    font.setWeight(QFont.DemiBold)
    font.setLetterSpacing(QFont.PercentageSpacing, theme.TRACKING)
    return font


class SectionTitle(QLabel):
    """A small-caps title, e.g. 'AUDIO'. tone: 'accent' (default) or 'dim'."""

    def __init__(self, text: str, tone: str = 'accent', parent: QWidget | None = None):
        super().__init__(text, parent)
        set_role(self, 'section', tone=tone)
        self.setFont(title_font())


class Card(QFrame):
    """A rounded panel: an optional title above a body layout.

    Add content with addWidget() / addLayout(), which go to the body. `body`
    picks the body layout (vertical by default); `margins` overrides the
    padding (left, top, right, bottom).
    """

    def __init__(self, title: str | None = None, *, tone: str = 'accent', body: QBoxLayout | None = None,
                 margins: tuple[int, int, int, int] | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        set_role(self, 'card')
        self.setAttribute(Qt.WA_StyledBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(*(margins or (theme.CARD_PAD_X, theme.CARD_PAD_Y,
                                               theme.CARD_PAD_X, theme.CARD_PAD_Y)))
        outer.setSpacing(6)

        self.title = SectionTitle(title, tone) if title else None
        if self.title is not None:
            outer.addWidget(self.title)

        self.body = body if body is not None else QVBoxLayout()
        self.body.setContentsMargins(0, 0, 0, 0)
        outer.addLayout(self.body, stretch=1)

    def addWidget(self, widget: QWidget, stretch: int = 0) -> None:
        self.body.addWidget(widget, stretch)

    def addLayout(self, layout: QLayout, stretch: int = 0) -> None:
        self.body.addLayout(layout, stretch)


class PlainTextLabel(QLabel):
    """A label that shows rich text built from plain text.

    text() returns exactly the plain text given to setText(), so callers and
    tests read what they wrote; subclasses decide how it looks in _html().
    """

    def __init__(self, text: str = '', parent: QWidget | None = None):
        super().__init__(parent)
        self._plain = ''
        self.setTextFormat(Qt.RichText)
        self.setText(text)

    def setText(self, text: str) -> None:
        self._plain = text
        super().setText(self._html(text))

    def text(self) -> str:
        return self._plain

    def _html(self, plain: str) -> str:
        return html.escape(plain).replace('\n', '<br>')


def _span(text: str, *, color: str, size: int, family: str, weight: int = 400, tracking: float = 0) -> str:
    spacing = f' letter-spacing:{tracking}px;' if tracking else ''
    return (f'<span style="color:{color}; font-size:{size}px; font-family:\'{family}\';'
            f' font-weight:{weight};{spacing}">{html.escape(text)}</span>')


class IndicatorTile(PlainTextLabel):
    """'LOW\\n2': a small muted label over a big mono number in the tone's colour.

    tone: a TILE_TONES key ('neutral', 'low', 'high'); value_size: the
    number's pixel size. The caller sets the tile's fixed size.
    """

    def __init__(self, text: str, tone: str = 'neutral', value_size: int = theme.SIZE_BODY + 2,
                 parent: QWidget | None = None):
        self._color = TILE_TONES[tone]
        self._value_size = value_size
        super().__init__(text, parent)
        set_role(self, 'tile', tone=tone)
        self.setAlignment(Qt.AlignCenter)

    def _html(self, plain: str) -> str:
        label, _, value = plain.partition('\n')
        top = _span(label, color=theme.TEXT_MUTED, size=theme.SIZE_SECTION - 1, family=theme.UI_FONT,
                    weight=600, tracking=1)
        bottom = _span(value, color=self._color, size=self._value_size, family=theme.MONO_FONT, weight=700)
        return f'{top}<br>{bottom}'


class ValueLabel(PlainTextLabel):
    """'Quiet: 1200': the name dim, the value bright and mono. Text without
    ': ' is shown whole as a value (for readouts like '100%')."""

    def __init__(self, text: str = '', parent: QWidget | None = None):
        super().__init__(text, parent)
        set_role(self, 'value')

    def _html(self, plain: str) -> str:
        name, sep, value = plain.partition(': ')
        if not sep:
            name, value = '', plain
        shown = _span(value, color=theme.TEXT, size=theme.SIZE_LABEL, family=theme.MONO_FONT)
        if not name:
            return shown
        return _span(f'{name}:', color=theme.TEXT_DIM, size=theme.SIZE_LABEL, family=theme.UI_FONT) + ' ' + shown
