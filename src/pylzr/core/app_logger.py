import datetime
from PyQt5.QtCore import QObject, pyqtSignal

_COLOR_ERROR   = '#e74c3c'
_COLOR_WARNING = '#d4a017'
_COLOR_DEBUG   = '#666666'

_LEVEL_IDX = {'debug': 0, 'info': 1, 'warning': 2, 'error': 3, 'quiet': 99}


class AppLogger(QObject):
    """Central logging service. Emits (text, hex_color) for the GUI panel.

    Use the module-level `logger` singleton — do not instantiate directly.
    """

    message_logged = pyqtSignal(str, str)  # (formatted text, hex color)

    def __init__(self):
        super().__init__()
        self._min_level = _LEVEL_IDX['info']  # matches the Settings panel default

    def set_min_level(self, level: str):
        """'debug' | 'info' | 'warning' | 'error' | 'quiet'"""
        self._min_level = _LEVEL_IDX.get(level.lower(), 0)

    def _log(self, level: str, message: str, color: str, level_idx: int):
        if level_idx < self._min_level:
            return
        ts = datetime.datetime.now().strftime('%H:%M:%S')
        self.message_logged.emit(f'[{ts}] {level:<7} {message}', color)

    def debug(self, message: str, color: str = _COLOR_DEBUG):
        self._log('DEBUG', message, color, 0)

    def info(self, message: str, color: str = ''):
        self._log('INFO', message, color, 1)

    def warning(self, message: str, color: str = _COLOR_WARNING):
        self._log('WARNING', message, color, 2)

    def error(self, message: str, color: str = _COLOR_ERROR):
        self._log('ERROR', message, color, 3)


logger = AppLogger()
