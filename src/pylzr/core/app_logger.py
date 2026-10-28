"""App-wide logging, built on Python's standard `logging` module.

Modules log through children of the 'pylzr' logger (see get_logger()). An
event can be tagged for colouring with `extra={'tone': Tone.X}`; each display
(the terminal formatter below, the in-app console in gui/log_panel.py) maps
tones and levels to its own colours, so logging code never deals in colours.

Nothing is shown until a display attaches a handler: the app entry point
calls configure_console_logging(), and the main window attaches the console
panel's handler.
"""

import logging
import sys
from enum import StrEnum

from . import text_styles as txt

LOGGER_NAME = 'pylzr'
LOG_FORMAT  = '[%(asctime)s] %(levelname)-7s %(message)s'
DATE_FORMAT = '%H:%M:%S'

# Settings-panel level names -> logging levels ('quiet' hides everything)
LEVELS = {'debug': logging.DEBUG, 'info': logging.INFO, 'quiet': logging.CRITICAL + 1}


class Tone(StrEnum):
    ON     = 'on'       # something switched on / connected
    OFF    = 'off'      # something switched off
    MODE   = 'mode'     # sound-mode change sent
    KEY    = 'key'      # keyboard note
    MUTED  = 'muted'    # settings changes
    NOTICE = 'notice'   # heads-up, e.g. unimplemented feature


_app_logger = logging.getLogger(LOGGER_NAME)
_app_logger.setLevel(logging.DEBUG)              # handlers decide what to show
_app_logger.addHandler(logging.NullHandler())    # no fallback stderr output


def get_logger(name: str) -> logging.Logger:
    """Logger for one part of the app, e.g. get_logger('midi')."""
    return logging.getLogger(f'{LOGGER_NAME}.{name}')


def tone_of(record: logging.LogRecord) -> Tone | None:
    return getattr(record, 'tone', None)


class ConsoleFormatter(logging.Formatter):
    """LOG_FORMAT lines, coloured with ANSI codes when `color` is true."""

    _TONE_COLORS  = {Tone.ON: txt.GREEN, Tone.OFF: txt.RED, Tone.MODE: txt.WHITE,
                     Tone.KEY: txt.CYAN, Tone.NOTICE: txt.YELLOW}
    _LEVEL_COLORS = {logging.ERROR: txt.RED, logging.WARNING: txt.YELLOW}

    def __init__(self, color: bool):
        super().__init__(LOG_FORMAT, DATE_FORMAT)
        self._color = color

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        if not self._color:
            return text
        code = self._TONE_COLORS.get(tone_of(record)) or self._LEVEL_COLORS.get(record.levelno)
        return f'{code}{text}{txt.RESET}' if code else text


class _SafeStreamHandler(logging.StreamHandler):
    """Never fails on characters the stream's encoding lacks (e.g. '→' when
    output is piped on Windows, which uses cp1252); they're replaced."""

    def format(self, record: logging.LogRecord) -> str:
        text = super().format(record)
        encoding = getattr(self.stream, 'encoding', None)
        if encoding:
            text = text.encode(encoding, errors='replace').decode(encoding)
        return text


def configure_console_logging(stream=None) -> logging.Handler:
    """Show every app log line (debug and up) in the terminal. Colours are
    used only when the stream is a terminal."""
    stream = stream or sys.stdout
    handler = _SafeStreamHandler(stream)
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(ConsoleFormatter(color=getattr(stream, 'isatty', lambda: False)()))
    _app_logger.addHandler(handler)
    return handler
