from PyQt5.QtCore import QSettings

from ..core import (
    AVG_COUNT_RATE_DEFAULT, CONTROL_MODES, DEFAULT_HIGH_THRESHOLDS, DEFAULT_LOW_THRESHOLDS,
    DMX_DEFAULT_NODE_IP,
)
from ..dmx import PortAddress, is_ipv4

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
    invalid. set() saves immediately, so nothing is lost if the app is killed.
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
        self._qs.sync()

    def clear(self):
        self._qs.clear()
        self._qs.sync()
