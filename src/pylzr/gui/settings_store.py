from pathlib import Path

from PyQt5.QtCore import QCoreApplication, QEvent, QSettings, QTimer

from ..core import (
    AVG_COUNT_RATE_DEFAULT, CONTROL_MODES, DEFAULT_HIGH_THRESHOLDS, DEFAULT_LOW_THRESHOLDS,
    DMX_DEFAULT_NODE_IP,
)
from ..core.app_logger import get_logger
from ..dmx import PortAddress, is_ipv4

log = get_logger('settings')        # 'pylzr.settings'

# Changes reach the file this long after the last one (design Q3). Dragging a
# slider changes a setting on every step, and each write takes a few ms on the
# GUI thread, so a drag is written once, after it ends.
FLUSH_MS = 400


class _DeferredSettings(QSettings):
    """QSettings that writes only when sync() is called (or when it's deleted).
    Plain QSettings also writes on the next event-loop pass after any change
    (it posts itself an UpdateRequest), which would defeat FLUSH_MS."""

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.UpdateRequest:
            return True                                   # ignored: SettingsStore decides when to write
        return super().event(event)


def _app_exists() -> bool:
    """Whether a QCoreApplication exists, so the flush timer can run. A
    function so tests can make the store act as if there were none."""
    return QCoreApplication.instance() is not None


# key -> default. Sound mode is deliberately not saved: the app always starts
# with it off.
DEFAULTS = {
    'cutoffs/low':         list(DEFAULT_LOW_THRESHOLDS),
    'cutoffs/high':        list(DEFAULT_HIGH_THRESHOLDS),
    'analysis/count_rate': AVG_COUNT_RATE_DEFAULT,
    'analysis/fft_window': 'rectangle',
    'display/smoothing':   0.0,
    'audio/gain':          1.0,
    'audio/device':        '',     # input device name; '' = system default
    'midi/port':           '',     # MIDI Out label; '' = automatic choice
    'app/log_level':       'info',
    'app/control_mode':    CONTROL_MODES[0],
    'dmx/node_ip':         DMX_DEFAULT_NODE_IP,
    'dmx/port_address':    [0, 0, 0],   # Art-Net net, subnet, universe
}


def _is_port_address(values: list[int]) -> bool:
    try:
        PortAddress(*values)
        return True
    except ValueError:
        return False


# Extra checks for values that can be read but still be unusable (e.g. a
# hand-edited file); failing values fall back to the default like
# unreadable ones.
_VALID = {
    'app/control_mode': lambda mode: mode in CONTROL_MODES,
    'dmx/node_ip':      is_ipv4,
    'dmx/port_address': _is_port_address,
}


class SettingsStore:
    """The user's saved settings: one .ini file in the user's config folder
    (%APPDATA%\\PyLZR on Windows, ~/.config/PyLZR on macOS/Linux).

    get() returns the saved value, or the default if missing, unreadable or
    invalid. set() stores the value at once (get() returns it) and writes the
    file FLUSH_MS after the last change, so dragging a slider writes once, not
    on every step; flush() writes now (the window calls it on close). Without
    a QCoreApplication there's no timer, and set() writes at once. Use it from
    the GUI thread only.
    """

    def __init__(self):
        self._qs = _DeferredSettings(QSettings.IniFormat, QSettings.UserScope, 'PyLZR', 'PyLZR')
        self._flush_timer = QTimer()                  # GUI thread; no parent: owned by this store
        self._flush_timer.setSingleShot(True)
        self._flush_timer.setInterval(FLUSH_MS)       # read here, so tests can patch FLUSH_MS before creating a store
        self._flush_timer.timeout.connect(self.flush)
        self._write_failure_logged = False            # QSettings.status() keeps its first error: log it once

    @property
    def pending(self) -> bool:
        """A change is waiting for the flush timer."""
        return self._flush_timer.isActive()

    @property
    def path(self) -> str:
        return self._qs.fileName()

    @property
    def fixtures_folder(self) -> Path:
        """Your fixtures folder (patch, profiles, bindings), next to the .ini file.
        Clearing the settings leaves it alone."""
        return Path(self.path).parent / 'fixtures'

    def get(self, key: str):
        default = DEFAULTS[key]
        raw = self._qs.value(key)
        if raw is None:
            return default
        try:
            if isinstance(default, list):     # stored as an ini list of strings
                values = [int(v) for v in (raw if isinstance(raw, list) else [raw])]
                value = values if len(values) == len(default) else default
            else:
                value = type(default)(raw)
        except (TypeError, ValueError):
            return default
        return value if _VALID.get(key, lambda _: True)(value) else default

    def set(self, key: str, value):
        if key not in DEFAULTS:
            raise KeyError(key)
        self._qs.setValue(key, value)
        if _app_exists():
            self._flush_timer.start()                 # (re)start: written FLUSH_MS after the last change
        else:
            self._sync()

    def flush(self):
        """Write pending changes now. Cheap when nothing is pending."""
        self._flush_timer.stop()
        self._sync()

    def clear(self):
        """Remove every saved setting, in the file too, at once."""
        self._flush_timer.stop()
        self._qs.clear()
        self._sync()

    def _sync(self):
        self._qs.sync()
        if self._qs.status() != QSettings.NoError and not self._write_failure_logged:
            self._write_failure_logged = True
            log.warning(f'Settings: could not write {self.path}; changes are kept and written at the next '
                        'change or when PyLZR closes')
