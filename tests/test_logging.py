import io
import logging
import threading

import pytest

from pylzr.core.app_logger import ConsoleFormatter, Tone, configure_console_logging, get_logger
from pylzr.core import text_styles as txt
from pylzr.gui import LogPanel
from pylzr.gui import theme

from helpers import wait_until

log = get_logger('test')


@pytest.fixture
def console():
    """Terminal handler writing to a buffer instead of stdout."""
    stream = io.StringIO()
    handler = configure_console_logging(stream)
    yield stream
    logging.getLogger('pylzr').removeHandler(handler)


@pytest.fixture
def panel(qapp):
    panel = LogPanel()
    logging.getLogger('pylzr').addHandler(panel.log_handler)
    yield panel
    logging.getLogger('pylzr').removeHandler(panel.log_handler)


def panel_lines(panel):
    return panel._text.toPlainText().splitlines()


def test_terminal_shows_every_level_in_the_console_format(console):
    log.debug('averages line')
    log.info('Sound mode: ON', extra={'tone': Tone.ON})
    lines = console.getvalue().splitlines()
    assert len(lines) == 2
    assert lines[0].endswith('DEBUG   averages line')
    assert lines[1].endswith('INFO    Sound mode: ON')
    assert lines[1].startswith('[') and lines[1][9] == ']'     # [HH:MM:SS]
    assert '\033[' not in console.getvalue()     # not a terminal → no colour codes


def test_terminal_survives_characters_its_encoding_lacks():
    """Windows pipes default to cp1252, which has no '→' (used in key logs)."""
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding='cp1252', write_through=True)
    handler = configure_console_logging(stream)
    try:
        log.info('Key: q → MIDI 73')
    finally:
        logging.getLogger('pylzr').removeHandler(handler)
    assert raw.getvalue().decode('cp1252').rstrip().endswith('Key: q ? MIDI 73')


@pytest.mark.parametrize('level, tone, color', [
    (logging.INFO,    Tone.ON,  txt.GREEN),
    (logging.INFO,    Tone.OFF, txt.RED),
    (logging.INFO,    Tone.KEY, txt.CYAN),
    (logging.ERROR,   None,     txt.RED),
    (logging.WARNING, None,     txt.YELLOW),
    (logging.INFO,    None,     ''),
])
def test_terminal_colours(level, tone, color):
    record = logging.LogRecord('pylzr.test', level, __file__, 1, 'msg', None, None)
    if tone:
        record.tone = tone
    text = ConsoleFormatter(color=True).format(record)
    assert text == (f'{color}{ConsoleFormatter(color=False).format(record)}{txt.RESET}' if color
                    else ConsoleFormatter(color=False).format(record))


def test_panel_hides_debug_by_default_and_follows_level(panel):
    log.debug('hidden')
    log.info('shown')
    panel.set_level('debug')
    log.debug('now shown')
    panel.set_level('quiet')
    log.error('quiet hides even errors')
    lines = panel_lines(panel)
    assert [line.split(maxsplit=2)[2] for line in lines] == ['shown', 'now shown']


def test_panel_colours_by_tone_then_level(panel):
    colors = []
    panel.log_handler.bridge.formatted.connect(lambda text, color: colors.append(color))
    log.info('plain')
    log.info('mode', extra={'tone': Tone.MODE})
    log.warning('careful')
    log.error('broken', extra={'tone': Tone.OFF})
    assert colors == ['', theme.LOG_TONES[Tone.MODE], theme.LOG_LEVELS[logging.WARNING],
                      theme.LOG_TONES[Tone.OFF]]


def test_logging_from_another_thread_reaches_panel(panel):
    worker = threading.Thread(target=lambda: log.info('from a worker thread'))
    worker.start()
    worker.join()
    wait_until(lambda: any('from a worker thread' in line for line in panel_lines(panel)))
