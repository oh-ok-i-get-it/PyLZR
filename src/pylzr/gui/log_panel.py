import logging
from collections import deque
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QTextEdit
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QColor, QTextCharFormat, QTextBlockFormat, QTextCursor
from . import theme
from ..core.app_logger import DATE_FORMAT, LEVELS, LOG_FORMAT, tone_of

_BG_STYLE = 'QTextEdit {{ background-color: #1a1a1a; color: {fg}; border: 1px solid #333; }}'
_DEFAULT_FG = '#d4d4d4'

_MAX_LOG_LINES = 2000   # oldest console lines are dropped beyond this
_AVG_ROWS      = 10


def _record_color(record: logging.LogRecord) -> str:
    """A tagged tone wins; otherwise colour by level ('' = default text)."""
    return theme.LOG_TONES.get(tone_of(record)) or theme.LOG_LEVELS.get(record.levelno, '')


class _LogHandler(logging.Handler):
    """Formats records and hands them to the panel through a Qt signal, so
    logging from any thread is delivered on the GUI thread."""

    class _Bridge(QObject):
        formatted = pyqtSignal(str, str)   # (text, hex color)

    def __init__(self):
        super().__init__(level=logging.INFO)   # matches the Settings panel default
        self.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
        self.bridge = self._Bridge()

    def emit(self, record: logging.LogRecord):
        try:
            self.bridge.formatted.emit(self.format(record), _record_color(record))
        except Exception:
            self.handleError(record)


def _base_text_widget(height: int) -> QTextEdit:
    t = QTextEdit()
    t.setReadOnly(True)
    t.setFixedHeight(height)
    t.setLineWrapMode(QTextEdit.NoWrap)
    doc = t.document()
    doc.setDocumentMargin(2)
    return t


class LogPanel(QWidget):
    """In-app console for the app's log.

    Attach `log_handler` to the 'pylzr' logger to show its records here;
    set_level() filters what is shown ('debug' | 'info' | 'quiet').
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 2, 4, 4)
        layout.setSpacing(2)
        layout.addWidget(QLabel('Console'))
        self._text = _base_text_widget(130)
        self._text.setStyleSheet(_BG_STYLE.format(fg=_DEFAULT_FG))
        self._text.document().setMaximumBlockCount(_MAX_LOG_LINES)
        layout.addWidget(self._text)
        self.setLayout(layout)

        self.log_handler = _LogHandler()
        self.log_handler.bridge.formatted.connect(self.append_message)

    def set_level(self, level: str):
        self.log_handler.setLevel(LEVELS[level])

    @pyqtSlot(str, str)
    def append_message(self, text: str, color: str):
        cursor = self._text.textCursor()
        cursor.movePosition(QTextCursor.End)

        if not self._text.document().isEmpty():
            block_fmt = QTextBlockFormat()
            block_fmt.setTopMargin(0)
            block_fmt.setBottomMargin(0)
            cursor.insertBlock(block_fmt)

        char_fmt = QTextCharFormat()
        char_fmt.setForeground(QColor(color if color else _DEFAULT_FG))
        cursor.mergeCharFormat(char_fmt)
        cursor.insertText(text)

        self._text.setTextCursor(cursor)
        self._text.ensureCursorVisible()


class AvgPanel(QWidget):
    """Scrolling display of the _AVG_ROWS most recent low/high windowed averages."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: deque[tuple[float, float]] = deque(maxlen=_AVG_ROWS)
        layout = QVBoxLayout()
        layout.setContentsMargins(4, 2, 4, 4)
        layout.setSpacing(2)
        layout.addWidget(QLabel('Averages'))
        self._text = _base_text_widget(130)
        self._text.setStyleSheet(_BG_STYLE.format(fg=_DEFAULT_FG))
        layout.addWidget(self._text)
        self.setLayout(layout)

    def append_avgs(self, low_avg: float, high_avg: float):
        self._entries.append((low_avg, high_avg))

        lines = [
            f'<span style="color:{theme.LOW_BAND}">L {lo:>9.4f}</span>'
            f'&nbsp;&nbsp;&nbsp;'
            f'<span style="color:{theme.HIGH_BAND}">H {hi:>9.4f}</span>'
            for lo, hi in self._entries
        ]
        self._text.setHtml(
            f'<div style="background:#1a1a1a; margin:0; padding:0;">{"<br>".join(lines)}</div>'
        )
        sb = self._text.verticalScrollBar()
        sb.setValue(sb.maximum())
