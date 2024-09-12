import textClass as txt

class SoundMode():
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

    def set_mode(self, low_avg, high_avg):
        if low_avg < self.low_quiet_mode_cutoff:
            self.low_mode = 0
        elif low_avg < self.LOW_MODE1_CUTOFF:
            self.low_mode = 1
        elif low_avg < self.LOW_MODE2_CUTOFF:
            self.low_mode = 2
        else: 
            self.low_mode = 3

        if high_avg < self.HIGH_MODE_QUIET_CUTOFF:
            self.high_mode = 0
        elif high_avg < self.HIGH_MODE1_CUTOFF:
            self.high_mode = 1
        elif high_avg < self.HIGH_MODE2_CUTOFF:
            self.high_mode = 2
        else: 
            self.high_mode = 3
        
    
    def update_mode(self):
        lm = self.low_mode
        hm = self.high_mode
        match lm: 
            case 0:
                text = txt.YELLOW + txt.I + "\n>>>> SM: " + txt.B + "LOW" + txt.BOFF + " 0 SENT \t" + txt.RESET
                match hm:
                    case 0:
                        self.send_mode(text, 108, txt.YELLOW, '0')
                    case 1:
                        self.send_mode(text, 60, txt.BLUE, '1')
                    case 2:
                        self.send_mode(text, 61, txt.CYAN, '2')
                    case 3:
                        self.send_mode(text, 62, txt.PURPLE, '3')
            case 1:
                text = txt.BLUE + txt.I + "\n>>>> SM: " + txt.B + "LOW" + txt.BOFF + " 1 SENT \t" + txt.RESET
                match hm:
                    case 0:
                        self.send_mode(text, 63, txt.YELLOW, '0')
                    case 1:
                        self.send_mode(text, 64, txt.BLUE, '1')
                    case 2:
                        self.send_mode(text, 65, txt.CYAN, '2')
                    case 3: 
                        self.send_mode(text, 66, txt.PURPLE, '3')
            case 2:
                text = txt.CYAN + txt.I + "\n>>>> SM: " + txt.B + "LOW" + txt.BOFF + " 2 SENT \t" + txt.RESET
                match hm:
                    case 0:
                        self.send_mode(text, 67, txt.YELLOW, '0')
                    case 1:
                        self.send_mode(text, 68, txt.BLUE, '1')
                    case 2:
                        self.send_mode(text, 69, txt.CYAN, '2')
                    case 3:
                        self.send_mode(text, 70, txt.PURPLE, '3')
            case 3:
                text = txt.PURPLE + txt.I + "\n>>>> SM: " + txt.B + "LOW" + txt.BOFF + " 3 SENT \t" + txt.RESET
                match hm:
                    case 0:
                        self.send_mode(text, 71, txt.YELLOW, '0')
                    case 1:
                        self.send_mode(text, 73, txt.BLUE, '1')
                    case 2:
                        self.send_mode(text, 74, txt.CYAN, '2')
                    case 3:
                        self.send_mode(text, 75, txt.PURPLE, '3')


    def check_mode(self, low_avg, high_avg):
        self.low_prev_mode = self.low_mode
        self.high_prev_mode = self.high_mode
        self.set_mode(low_avg, high_avg)

        if self.low_mode != self.low_prev_mode or self.high_mode != self.high_prev_mode:
            self.update_mode()


    def send_mode(self, text, midi_note, color, mode):
        self.midiout.press_MIDI_note(midi_note)
        print(text + "\t" + txt.B + color + "HIGH" + txt.BOFF + " " + mode + " SENT <<<<\n" + txt.IOFF)




### ADD METHOD TO CHANGE CUTOFF VARIABLES FOR MAIN FILE?

    def set_low_cutoff(self, cutoff, mode):
        match mode:
            case 0:
                self.low_quiet_mode_cutoff = cutoff
            case 1:
                self.LOW_MODE1_CUTOFF = cutoff
            case 2:
                self.LOW_MODE2_CUTOFF = cutoff
    
    def set_high_cutoff(self, cutoff, mode):
        match mode:
            case 0:
                self.HIGH_MODE_QUIET_CUTOFF = cutoff
            case 1:
                self.HIGH_MODE1_CUTOFF = cutoff
            case 2:
                self.HIGH_MODE2_CUTOFF = cutoff


        