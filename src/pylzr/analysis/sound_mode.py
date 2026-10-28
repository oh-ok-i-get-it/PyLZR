from bisect import bisect_right
from collections.abc import Sequence
from ..core import DM_SEMITONE_OFFSET, MIDI_SPACE_NOTE
from ..core import text_styles as txt
from ..core.app_logger import logger


class SoundMode:
    """Maps windowed frequency averages to MIDI notes via a 4x4 mode matrix.

    Maintains two independent threshold axes (low-band and high-band), each
    with three cutoff levels that divide the energy range into four modes
    (0-3). The (low_mode, high_mode) pair selects a MIDI note from MODE_MAP,
    which is then sent through the injected output object.

    output_handler must expose press_note(note: int).

    Extension point: to route mode changes to DMX or other outputs alongside
    (or instead of) MIDI, replace or wrap output_handler with an object that
    dispatches to multiple systems. A future refactor could accept a list of
    handlers each implementing on_mode_change(low_mode, high_mode, note).
    """

    # Terminal color per mode index (same scheme for both bands)
    MODE_COLOR = {0: txt.YELLOW, 1: txt.BLUE, 2: txt.CYAN, 3: txt.PURPLE}

    # MODE_MAP[low_mode][high_mode] -> base MIDI note
    MODE_MAP = {
        0: {0: MIDI_SPACE_NOTE, 1: 60, 2: 61, 3: 62},
        1: {0: 63,              1: 64, 2: 65, 3: 66},
        2: {0: 67,              1: 68, 2: 69, 3: 70},
        3: {0: 71,              1: 72, 2: 73, 3: 74},
    }

    def __init__(
        self,
        low_thresholds:  Sequence[float],   # (quiet, mode 1, mode 2) cutoffs
        high_thresholds: Sequence[float],
        output_handler,                      # any object with press_note(note: int)
        dm_toggle_rate: int = 120,
    ):
        self._output = output_handler

        self.low_mode  = -1
        self.high_mode = -1

        self.dm_on         = True
        self.dm_mode_label = 1

        self._low_thresholds  = list(low_thresholds)
        self._high_thresholds = list(high_thresholds)

        self._dm_count       = 0
        self._dm_toggle_rate = dm_toggle_rate

    def set_mode(self, low_avg: float, high_avg: float):
        self.low_mode  = bisect_right(self._low_thresholds,  low_avg)
        self.high_mode = bisect_right(self._high_thresholds, high_avg)

    def update_mode(self):
        lm, hm = self.low_mode, self.high_mode
        text = (
            f"{self.MODE_COLOR[lm]}{txt.I}"
            f"\n>>>> SM: {txt.B}LOW{txt.BOFF} {lm} SENT \t{txt.RESET}"
        )
        midi_base = self.MODE_MAP[lm][hm]

        if (not self.dm_on) or (midi_base == MIDI_SPACE_NOTE):
            note       = midi_base
            mode_label = 1
        else:
            note       = midi_base + DM_SEMITONE_OFFSET
            mode_label = 2

        self.dm_mode_label = mode_label
        self._output.press_note(note)
        print(f"{text}\t{txt.B}{self.MODE_COLOR[hm]}HIGH{txt.BOFF} {hm} SENT <<<<\n{txt.IOFF}")
        print(f"{txt.WHITE}\t|| DUAL MODE: {mode_label} ||\n\tMIDI NOTE: {note}")
        logger.info(f'SoundMode: LOW={lm} HIGH={hm} | DualMode={mode_label} | MIDI={note}', '#ffffff')

    def check_mode(self, low_avg: float, high_avg: float):
        prev = (self.low_mode, self.high_mode)
        self.set_mode(low_avg, high_avg)
        if (self.low_mode, self.high_mode) != prev:
            self.update_mode()

    def advance_dm_counter(self):
        self._dm_count += 1
        if self._dm_count >= self._dm_toggle_rate:
            self.toggle_dm_mode()
            self._dm_count = 0

    def set_dm_toggle_rate(self, rate: float):
        self._dm_toggle_rate = rate

    def toggle_dm_mode(self):
        self.dm_on = not self.dm_on

    @property
    def dm_countdown(self) -> int:
        return int(self._dm_toggle_rate - self._dm_count)

    def set_cutoff(self, cutoff: float, mode: int, *, high: bool = False):
        if high:
            self._high_thresholds[mode] = cutoff
        else:
            self._low_thresholds[mode] = cutoff
