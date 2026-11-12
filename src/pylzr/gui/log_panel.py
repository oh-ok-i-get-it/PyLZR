import logging
from collections import deque
from PyQt5.QtWidgets import QTextEdit
from PyQt5.QtCore import QObject, QSize, QUrl, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor, QTextCharFormat, QTextBlockFormat, QTextCursor, QTextDocument, QTextImageFormat
from . import style, theme
from .widgets import Card, set_role
from ..core.app_logger import DATE_FORMAT, LEVELS, tone_of

# Each panel is a card (dim title + text); the text box itself is borderless on it
_CARD_MARGINS = (10, 9, 6, 6)   # tight on the right / bottom, where the scroll bars sit
_DEFAULT_FG   = theme.TEXT

# Console lines: time, then the message. The level shows as colour, and as an
# icon for warnings and errors. (The terminal keeps core's LOG_FORMAT.)
_PANEL_FORMAT = '%(asctime)s  %(message)s'
_SEPARATOR    = '  '                        # between the time and the message; the icon goes after it
_LEVEL_ICONS  = ((logging.ERROR, 'circle-x', theme.ERROR), (logging.WARNING, 'triangle-alert', theme.WARN))
_ICON_SIZE    = theme.SIZE_LABEL - 1        # px, about the height of the text's capitals

_MAX_LOG_LINES = 2000   # oldest console lines are dropped beyond this
_AVG_ROWS      = 10


def _record_color(record: logging.LogRecord) -> str:
    """A tagged tone wins; otherwise colour by level ('' = default text)."""
    return theme.LOG_TONES.get(tone_of(record)) or theme.LOG_LEVELS.get(record.levelno, '')


class _LogHandler(logging.Handler):
    """Formats records and hands them to the panel through a Qt signal, so
    logging from any thread is delivered on the GUI thread."""

    class _Bridge(QObject):
        formatted = pyqtSignal(str, str, int)   # (text, hex color, logging level)

    def __init__(self):
        super().__init__(level=logging.INFO)   # matches the Settings panel default
        self.setFormatter(logging.Formatter(_PANEL_FORMAT, DATE_FORMAT))
        self.bridge = self._Bridge()

    def emit(self, record: logging.LogRecord):
        try:
            self.bridge.formatted.emit(self.format(record), _record_color(record), record.levelno)
        except Exception:
            self.handleError(record)


def _level_icon(level: int) -> tuple[str, str] | None:
    """(icon name, colour) for a warning or worse; None below that."""
    for at_least, name, colour in _LEVEL_ICONS:
        if level >= at_least:
            return name, colour
    return None


def _base_text_widget(height: int) -> QTextEdit:
    t = QTextEdit()
    set_role(t, 'log')
    t.setReadOnly(True)
    t.setFixedHeight(height)
    t.setLineWrapMode(QTextEdit.NoWrap)
    doc = t.document()
    doc.setDocumentMargin(2)
    return t


class LogPanel(Card):
    """In-app console for the app's log.

    Attach `log_handler` to the 'pylzr' logger to show its records here;
    set_level() filters what is shown ('debug' | 'info' | 'quiet').
    """

    def __init__(self, parent=None):
        super().__init__('CONSOLE', tone='dim', margins=_CARD_MARGINS, parent=parent)
        self._text = _base_text_widget(130)
        self._text.document().setMaximumBlockCount(_MAX_LOG_LINES)
        self.addWidget(self._text)

        self.log_handler = _LogHandler()
        self.log_handler.bridge.formatted.connect(self.append_message)

    def set_level(self, level: str):
        self.log_handler.setLevel(LEVELS[level])

    def _icon_format(self, name: str, colour: str) -> QTextImageFormat:
        """An inline image of the icon, added to the document the first time."""
        url = f'pylzr-icon:{name}'
        doc = self._text.document()
        if doc.resource(QTextDocument.ImageResource, QUrl(url)) is None:
            pixmap = style.icon(name, colour, size=_ICON_SIZE).pixmap(QSize(_ICON_SIZE, _ICON_SIZE) * 2)
            doc.addResource(QTextDocument.ImageResource, QUrl(url), pixmap.toImage())
        fmt = QTextImageFormat()
        fmt.setName(url)
        fmt.setWidth(_ICON_SIZE)
        fmt.setHeight(_ICON_SIZE)
        fmt.setVerticalAlignment(QTextCharFormat.AlignBaseline)   # AlignMiddle makes the line 2 px taller
        return fmt

    @pyqtSlot(str, str, int)
    def append_message(self, text: str, color: str, level: int = logging.INFO):
        """Add a line in `color` ('' = default). A warning or error gets its
        icon after the time (text is 'HH:MM:SS  message')."""
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.End)

        if not self._text.document().isEmpty():
            block_fmt = QTextBlockFormat()
            block_fmt.setTopMargin(0)
            block_fmt.setBottomMargin(0)
            cursor.insertBlock(block_fmt)

        char_fmt = QTextCharFormat()
        char_fmt.setForeground(QColor(color if color else _DEFAULT_FG))
        icon = _level_icon(level)
        head, sep, message = text.partition(_SEPARATOR)
        if icon is None or not sep:
            cursor.insertText(text, char_fmt)
        else:
            cursor.insertText(head + sep, char_fmt)
            cursor.insertImage(self._icon_format(*icon))
            cursor.insertText(' ' + message, char_fmt)

        self._text.setTextCursor(cursor)
        self._text.ensureCursorVisible()


class AvgPanel(Card):
    """Scrolling display of the _AVG_ROWS most recent low/high windowed averages."""

    def __init__(self, parent=None):
        super().__init__('AVERAGES', tone='dim', margins=_CARD_MARGINS, parent=parent)
        self._entries: deque[tuple[float, float]] = deque(maxlen=_AVG_ROWS)
        self._text = _base_text_widget(130)
        self.addWidget(self._text)

    def append_avgs(self, low_avg: float, high_avg: float):
        self._entries.append((low_avg, high_avg))

        lines = [   # whole numbers (cutoffs top out at 40000), right-aligned (white-space: pre keeps the padding)
            f'<span style="color:{theme.LOW_BAND}">L {lo:>5.0f}</span>'
            f'   '
            f'<span style="color:{theme.HIGH_BAND}">H {hi:>5.0f}</span>'
            for lo, hi in self._entries
        ]
        self._text.setHtml(f'<div style="margin:0; padding:0; white-space:pre;">{"<br>".join(lines)}</div>')
        sb = self._text.verticalScrollBar()
        sb.setValue(sb.maximum())
