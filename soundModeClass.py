import textClass as txt
from bisect import bisect_right

class SoundMode():
    # const lookup tables
    LOW_COLOR = {
        0: txt.YELLOW,
        1: txt.BLUE,
        2: txt.CYAN,
        3: txt.PURPLE,
    }

    HIGH_COLOR = {
        0: txt.YELLOW,
        1: txt.BLUE,
        2: txt.CYAN,
        3: txt.PURPLE,
    }

    MODE_MAP = {
        0: {0: "SPACE", 1: 60,  2: 61,  3: 62},
        1: {0: 63,       1: 64,  2: 65,  3: 66},
        2: {0: 67,       1: 68,  2: 69,  3: 70},
        3: {0: 71,       1: 72,  2: 73,  3: 74},
    }

    _CUT_ATTRS = {
        'low':  ['low_quiet_mode_cutoff', 'LOW_MODE1_CUTOFF', 'LOW_MODE2_CUTOFF'],
        'high': ['HIGH_MODE_QUIET_CUTOFF', 'HIGH_MODE1_CUTOFF', 'HIGH_MODE2_CUTOFF'],
    }



    def __init__(self, 
                 low_quiet_mode_cutoff, 
                 LOW_MODE1_CUTOFF, 
                 LOW_MODE2_CUTOFF, 
                 HIGH_MODE_QUIET_CUTOFF, 
                 HIGH_MODE1_CUTOFF, 
                 HIGH_MODE2_CUTOFF, 
                 midiout):
        #fields
        self.midiout = midiout

        self.low_quiet_mode_cutoff = low_quiet_mode_cutoff
        self.LOW_MODE1_CUTOFF = LOW_MODE1_CUTOFF
        self.LOW_MODE2_CUTOFF = LOW_MODE2_CUTOFF
        
        self.HIGH_MODE_QUIET_CUTOFF = HIGH_MODE_QUIET_CUTOFF
        self.HIGH_MODE1_CUTOFF = HIGH_MODE1_CUTOFF
        self.HIGH_MODE2_CUTOFF = HIGH_MODE2_CUTOFF

        self.low_mode = -1
        self.low_prev_mode = 0

        self.high_mode = -1
        self.high_prev_mode = 0

        # Dual Mode
        self.dm_ON = False

        self.SPACE = 106 #108

        # build mode cutoffs thresholds lists
        self._low_thresholds  = [
            self.low_quiet_mode_cutoff,
            self.LOW_MODE1_CUTOFF,
            self.LOW_MODE2_CUTOFF,
        ]
        self._high_thresholds = [
            self.HIGH_MODE_QUIET_CUTOFF,
            self.HIGH_MODE1_CUTOFF,
            self.HIGH_MODE2_CUTOFF,
        ]



    def set_mode(self, low_avg, high_avg):
        self.low_mode = bisect_right(self._low_thresholds, low_avg)
        self.high_mode = bisect_right(self._high_thresholds, high_avg)
        
    

    def update_mode(self):
        lm = self.low_mode
        hm = self.high_mode
        
        # build display text
        text = (
            f"{self.LOW_COLOR[lm]}{txt.I}"
            f"\n>>>> SM: {txt.B}LOW{txt.BOFF} {lm} SENT \t{txt.RESET}"
        )

        # base MIDI note
        offset = self.MODE_MAP[lm].get(hm, "SPACE")
        MIDI_base = self.SPACE if offset == "SPACE" else offset

        # Dual Mode midi behavior
        if (not self.dm_ON) or (MIDI_base == self.SPACE):
            note = MIDI_base
            mode_label = 1
        else:
            note = MIDI_base + 15
            mode_label = 2

        # send MIDI and print
        self.midiout.press_MIDI_note(note)
        color = self.HIGH_COLOR[hm]
        digit = str(hm)
        print(f"{text}\t{txt.B}{color}HIGH{txt.BOFF} {digit} SENT <<<<\n{txt.IOFF}")
        print(f"{txt.WHITE}\t|| DUAL MODE: {mode_label} ||\n\tMIDI NOTE: {note}")



    def check_mode(self, low_avg, high_avg):
        prev = (self.low_mode, self.high_mode)

        self.set_mode(low_avg, high_avg)

        if (self.low_mode, self.high_mode) != prev:
            self.update_mode()

    
            
    def toggle_dm_mode(self):
        self.dm_ON = (not self.dm_ON)



    def get_dm_mode_bool(self):
        return self.dm_ON



def set_cutoff(self, cutoff: float, mode: int, *, high: bool = False):
    key = 'high' if high else 'low'
    attr_name = self._CUT_ATTRS[key][mode]
    setattr(self, attr_name, cutoff)
    if high:
        self._high_thresholds[mode] = cutoff
    else:
        self._low_thresholds[mode] = cutoff




