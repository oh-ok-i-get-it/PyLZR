import time
import rtmidi as midi
import textClass as txt

class VirtualMIDI():
    def __init__(self):
        # MIDI
        self.midiout = midi.MidiOut()
        self.available_ports = self.midiout.get_ports()

        if self.available_ports:
            self.midiout.open_port(0)
        else: 
            self.midiout.open_virtual_port("PyLZR-MIDI")

        #SOUND MODE
        self.sm_ON = False

        #midi key constants
        self.SPACE = 108
        self.ONE = 60
        self.TWO = 61
        self.THREE = 62
        self.FOUR = 63
        self.FIVE = 64
        self.SIX = 65
        self.SEVEN = 66
        self.EIGHT = 67
        self.NINE = 68
        self.ZERO = 69
        self.DASH = 70
        self.EQUALS = 71
        self.TAB = 72
        self.Q = 73
        self.W = 74
        self.E = 75
        self.R = 76
        self.T = 77
        self.Y = 78
        self.U = 79
        self.I = 80
        self.O = 81
        self.P = 82


        self.SM_ON_TXT = txt.RESET + txt.B + txt.GREEN 
        self.SM_ON_TXT_B = txt.B + txt.GREENB + txt.BLACK
        self.SM_OFF_TXT = txt.RESET + txt.B + txt.RED
        self.SM_OFF_TXT_B = txt.B + txt.REDB + txt.BLACK


        self.keys = [
            49,
            50,
            51,
            52,
            53,
            54,
            55,
            56,
            57,
            48,
            45,
            61,
            16777217,
            81,
            87,
            69,
            82,
            84,
            89,
            85,
            73,
            79,
            80,
            91,
            93,
            65,
            83,
            68,
            70,
            71,
            72,
            74,
            75,
            76,
            59,
            39,
            16777220,
            16777248,
            90,
            88,
            67,
            86,
            66,
            78,
            77,
            44,
            46,
            47,
            32
        ]

        self.keys_names = [
            '1',
            '2',
            '3',
            '4',
            '5',
            '6',
            '7',
            '8',
            '9',
            '0',
            '-',
            '=',
            'TAB',
            'q',
            'w',
            'e',
            'r',
            't',
            'y',
            'u',
            'i',
            'o',
            'p',
            '[',
            ']',
            'a',
            's',
            'd',
            'f',
            'g',
            'h',
            'j',
            'k',
            'l',
            ';',
            '\'',
            'ENTER',
            'L_SHIFT',
            'z',
            'x',
            'c',
            'v',
            'b',
            'n',
            'm',
            ',',
            '.',
            '/',
            'SPACE'
        ]

        self.keys_midi_notes = [0]*50
        for i in range(50):
            self.keys_midi_notes[i] = 60 + i


    def keyboard(self, key_num):
        index = 0
        if key_num == 16777248:
            self.toggle_sm()
        else:
            if not self.sm_ON:
                for key in self.keys:
                    if key_num == key:
                        print(txt.B + txt.CYANB + txt.BLACK + "Pressed:" + txt.RESET + txt.CYAN + txt.B + " " + self.keys_names[index] + txt.RESET)
                        self.press_MIDI_note(self.keys_midi_notes[index])
                    index += 1

                
            
    def press_MIDI_note(self, note): 
        # MIDI
        NOTE_ON = 0x90
        NOTE_OFF = 0x80

        note_on = [NOTE_ON, note, 112] # channel 1, note# (60 is middle C), velocity (112?)
        note_off = [NOTE_OFF, note, 0]
        self.midiout.send_message(note_on)
        time.sleep(0.1)
        self.midiout.send_message(note_off)
        time.sleep(0.1)
        midiNote = str(note)
        #print("SEND MIDI: " + midiNote)


    def toggle_sm(self):
        if self.sm_ON:
            self.sm_ON = False
            print("\n" + self.SM_OFF_TXT + "#### " + self.SM_OFF_TXT_B + "SOUND MODE OFF" + self.SM_OFF_TXT + " ####\n" + txt.RESET)
        else:
            self.sm_ON = True
            print("\n" + self.SM_ON_TXT +"#### " + self.SM_ON_TXT_B + "SOUND MODE ON" + self.SM_ON_TXT + " ####\n" + txt.RESET)


if __name__ == '__main__':
    vm = VirtualMIDI()


     