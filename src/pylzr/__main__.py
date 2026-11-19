import atexit
import sys

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from .core.app_logger import configure_console_logging, get_logger
from .core.safety import EmergencyStop, install_excepthook

log = get_logger('app')

# Design Q1: after an unhandled exception the outputs are blacked out and the app keeps running
KEEP_RUNNING_HINT = ('PyLZR keeps running with DMX output stopped: switch Control Mode to MIDI and back to DMX to '
                     'send again. In MIDI mode the next cue lights the show again.')


def _quit_as_if_closed():
    """Ctrl+C (design Q8): close every window on the next event-loop pass, the
    same path as the user closing them (closeEvent, then the app quits)."""
    if QApplication.instance() is not None:
        QTimer.singleShot(0, QApplication.closeAllWindows)


def main():
    configure_console_logging()          # first, so anything that fails from here on is logged (M4)
    safety = EmergencyStop()
    install_excepthook(safety, on_handled=lambda: log.warning(KEEP_RUNNING_HINT),
                       on_interrupt=_quit_as_if_closed)
    atexit.register(safety.trigger, 'exit')   # registered after PyQt's import, so it runs before PyQt's own exit cleanup
    app = QApplication(sys.argv)
    from .gui import MainWindow, style  # imported here so QApplication exists before any widget module loads
    style.apply(app)                     # before any window: fonts, palette, stylesheet, plot colours
    window = MainWindow(safety=safety)
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()
