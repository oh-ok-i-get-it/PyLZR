# Every colour of the GUI, plus fonts and layout metrics. Other gui/ modules use
# these tokens instead of hex values (tests/test_style.py checks).
import logging

from ..core.app_logger import Tone

LOW_BAND  = '#d4a017'   # low-band values (mode display, averages)
HIGH_BAND = '#9b59b6'   # high-band values
ACCENT    = '#58a6ff'   # section titles, focus/hover, active gear
OK        = '#2ecc71'   # connected / on
WARN      = '#e3b341'   # working, but needs attention
ERROR     = '#e74c3c'   # disconnected / clipping
METER_MID = '#f39c12'   # middle of the signal level meter (green → orange → red)

# Surfaces, lines and text of the black UI (gui/style.py builds the app stylesheet from these)
BG            = '#000000'   # window and plot background
CARD          = '#0d0d0d'   # panels one step up from the background
RAISED        = '#141414'   # inputs and dropdowns
BUTTON        = '#161616'   # button face
BORDER        = '#1c1c1c'   # card edges
BORDER_STRONG = '#2a2a2a'   # input and button edges
HOVER_EDGE    = '#3a3a3a'   # edge of a dark tile-like button under the mouse
GROOVE        = '#2a2a2a'   # unfilled part of a slider
TEXT          = '#e6e8eb'   # values, button text
TEXT_DIM      = '#9aa0a6'   # labels
TEXT_MUTED    = '#5f6368'   # hints, status line
DISABLED      = '#444444'   # disabled text
WHITE         = '#ffffff'   # text on a solid colour (CLIP on), and for mixing lighter shades
OK_TINT       = '#0b2416'   # background of a small button that is on (OK green over black)
DIVIDER       = '#1e1e1e'   # 1 px lines between settings sections
DOT_OFF       = '#383838'   # a status dot with nothing to report (DMX off)
SCROLL_HANDLE = '#333333'   # scroll bar handle
SCROLL_HOVER  = '#444444'   # scroll bar handle under the mouse
AXIS          = '#7d838b'   # plot tick labels
AXIS_LINE     = '#3a3a3a'   # plot axis lines
GRID          = '#5a5a5a'   # plot grid pen (pyqtgraph's GridItem draws it much fainter)
MID_BAND      = '#6e7681'   # spectrum between the low and high bands
TOP_BAND      = '#3a3a3a'   # spectrum above the high band (shown, not analysed)

# Fonts (bundled in gui/assets/fonts) and pixel sizes
UI_FONT   = 'Inter'
MONO_FONT = 'JetBrains Mono'
SIZE_SECTION = 10   # small-caps section titles
SIZE_LABEL   = 11   # labels, status line, console
SIZE_BODY    = 12   # default text, buttons, inputs
SIZE_TITLE   = 14   # Sound Mode button
SIZE_NUMBER  = 20   # LOW / HIGH readouts

TRACKING = 112     # letter spacing of small-caps titles, % of normal (stylesheets can't set it)

RADIUS      = 6     # buttons, inputs
RADIUS_CARD = 8     # cards, panels, menus
TILE_BORDER = '#222222'   # indicator tile edge (LOW / HIGH tint it with their band colour)

# Layout metrics (px)
MARGIN      = 10    # window edge to content
GAP         = 8     # between neighbouring cards and rows
CARD_PAD_X  = 14    # card padding, left / right
CARD_PAD_Y  = 10    # card padding, top / bottom
TOP_ROW_H   = 64    # rate card, Sound Mode and tiles row
PLOT_AXIS_W = 52    # left axis width, the same on both plots so they line up

# In-app console colours: tagged tones first, then by log level
LOG_TONES = {
    Tone.ON:     OK,
    Tone.OFF:    ERROR,
    Tone.MODE:   WHITE,
    Tone.KEY:    '#00bcd4',
    Tone.MUTED:  '#8a8a8a',
    Tone.NOTICE: WARN,
}
LOG_LEVELS = {
    logging.DEBUG:   '#666666',
    logging.WARNING: '#d4a017',
    logging.ERROR:   ERROR,
}
