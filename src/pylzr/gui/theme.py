# Colors shared across GUI panels. Panel-specific shades stay in their modules.
import logging

from ..core.app_logger import Tone

LOW_BAND  = '#d4a017'   # low-band values (mode display, averages)
HIGH_BAND = '#9b59b6'   # high-band values
ACCENT    = '#58a6ff'   # section titles, focus/hover, active gear
OK        = '#2ecc71'   # connected / on
ERROR     = '#e74c3c'   # disconnected / clipping

# In-app console colours: tagged tones first, then by log level
LOG_TONES = {
    Tone.ON:     OK,
    Tone.OFF:    ERROR,
    Tone.MODE:   '#ffffff',
    Tone.KEY:    '#00bcd4',
    Tone.MUTED:  '#8a8a8a',
    Tone.NOTICE: '#e3b341',
}
LOG_LEVELS = {
    logging.DEBUG:   '#666666',
    logging.WARNING: '#d4a017',
    logging.ERROR:   ERROR,
}
