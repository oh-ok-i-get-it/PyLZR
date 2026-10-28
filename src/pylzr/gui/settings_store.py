from PyQt5.QtCore import QSettings

from ..core import AVG_COUNT_RATE_DEFAULT, DEFAULT_HIGH_THRESHOLDS, DEFAULT_LOW_THRESHOLDS

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
}


class SettingsStore:
    """The user's saved settings: one .ini file in the user's config folder
    (%APPDATA%\\PyLZR on Windows, ~/.config/PyLZR on macOS/Linux).

    get() returns the saved value, or the default if missing or unreadable.
    set() saves immediately, so nothing is lost if the app is killed.
    """

    def __init__(self):
        self._qs = QSettings(QSettings.IniFormat, QSettings.UserScope, 'PyLZR', 'PyLZR')

    @property
    def path(self) -> str:
        return self._qs.fileName()

    def get(self, key: str):
        default = DEFAULTS[key]
        raw = self._qs.value(key)
        if raw is None:
            return default
        try:
            if isinstance(default, list):     # stored as an ini list of strings
                values = [int(v) for v in (raw if isinstance(raw, list) else [raw])]
                return values if len(values) == len(default) else default
            return type(default)(raw)
        except (TypeError, ValueError):
            return default

    def set(self, key: str, value):
        if key not in DEFAULTS:
            raise KeyError(key)
        self._qs.setValue(key, value)
        self._qs.sync()

    def clear(self):
        self._qs.clear()
        self._qs.sync()
