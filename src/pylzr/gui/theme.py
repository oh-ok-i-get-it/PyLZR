# Colors shared across GUI panels. Panel-specific shades stay in their modules.
import logging

from ..core.app_logger import Tone

LOW_BAND  = '#d4a017'   # low-band values (mode display, averages)
HIGH_BAND = '#9b59b6'   # high-band values
ACCENT    = '#58a6ff'   # section titles, focus/hover, active gear
OK        = '#2ecc71'   # connected / on
WARN      = '#e3b341'   # working, but needs attention
ERROR     = '#e74c3c'   # disconnected / clipping

# Surfaces, lines and text of the black UI (gui/style.py builds the app stylesheet from these)
BG            = '#000000'   # window and plot background
CARD          = '#0d0d0d'   # panels one step up from the background
RAISED        = '#141414'   # inputs and dropdowns
BUTTON        = '#161616'   # button face
BORDER        = '#1c1c1c'   # card edges
BORDER_STRONG = '#2a2a2a'   # input and button edges
GROOVE        = '#2a2a2a'   # unfilled part of a slider
TEXT          = '#e6e8eb'   # values, button text
TEXT_DIM      = '#9aa0a6'   # labels
TEXT_MUTED    = '#5f6368'   # hints, status line
DISABLED      = '#444444'   # disabled text
AXIS          = '#7d838b'   # plot axes and tick labels

# Fonts (bundled in gui/assets/fonts) and pixel sizes
UI_FONT   = 'Inter'
MONO_FONT = 'JetBrains Mono'
SIZE_SECTION = 10   # small-caps section titles
SIZE_LABEL   = 11   # labels, status line, console
SIZE_BODY    = 12   # default text, buttons, inputs
SIZE_TITLE   = 14   # Sound Mode button
SIZE_NUMBER  = 20   # LOW / HIGH readouts

RADIUS      = 6     # buttons, inputs
RADIUS_CARD = 8     # cards, panels, menus

# In-app console colours: tagged tones first, then by log level
LOG_TONES = {
    Tone.ON:     OK,
    Tone.OFF:    ERROR,
    Tone.MODE:   '#ffffff',
    Tone.KEY:    '#00bcd4',
    Tone.MUTED:  '#8a8a8a',
    Tone.NOTICE: WARN,
}
LOG_LEVELS = {
    logging.DEBUG:   '#666666',
    logging.WARNING: '#d4a017',
    logging.ERROR:   ERROR,
}
