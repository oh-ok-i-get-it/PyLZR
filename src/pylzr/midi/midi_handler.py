import time
import rtmidi as midi
from ..utils import text_styles as txt
import threading

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
        self.SPACE = 106 #108
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
        #added for dual mode
        self.SQBRO = 83
        self.SQBRC = 84
        self.A = 85
        self.S = 86
        self.D = 87
        self.F = 88
        self.G = 89
        self.H = 90
        self.J = 91
        self.K = 92
        self.L = 93
        self.SEMI = 94
            #self.BSLASH
        self.APOSTROPHE = 95
        self.Z = 96
        self.X = 97
        self.C = 98
        #additional keys not used in dual mode
        self.V = 99
        self.B = 100
        self.N = 101
        self.M = 102
        self.COMMA = 103
        self.PERIOD = 104
        self.FSLASH = 105

        self.SM_ON_TXT = txt.RESET + txt.B + txt.GREEN 
        self.SM_ON_TXT_B = txt.B + txt.GREENB + txt.BLACK
        self.SM_OFF_TXT = txt.RESET + txt.B + txt.RED
        self.SM_OFF_TXT_B = txt.B + txt.REDB + txt.BLACK


        self.keys = [
            49, #1
            50, #2
            51, #3
            52, #4
            53, #5
            54, #6
            55, #7
            56, #8
            57, #9
            48, #0
            45, #-
            61, #=
            16777217,   #TAB
            81, #q
            87, #w
            69, #e
            82, #r
            84, #t
            89, #y
            85, #u
            73, #i
            79, #o
            80, #p
            91, #[
            93, #]
            65, #a
            83, #s
            68, #d
            70, #f
            71, #g
            72, #h
            74, #j
            75, #k
            76, #l
            59, #;
            39, #\
            #16777220,
            #16777248,
            90, #z
            88, #x
            67, #c
            86, #v
            66, #b
            78, #n
            77, #m
            44, #,
            46, #.
            47, #/
            32, #SPACE
            #moved
            16777220,   #ENTER
            16777248    #LSHIFT
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
            #'ENTER',
            #'L_SHIFT',
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
            'SPACE',
            #moved
            'ENTER',
            'L_SHIFT'
        ]

        self.keys_midi_notes = [0]*50
        for i in range(50):
            self.keys_midi_notes[i] = 60 + i


    def keyboard(self, key_num):
        index = 0
        if key_num == 16777248:
            self.toggle_sm()
        #DUAL MODE MANUAL TOGGLE ADDED 
        #elif key_num == 16777240:
        #    self.
        else:
            if not self.sm_ON:
                for key in self.keys:
                    if key_num == key:
                        print(txt.B + txt.CYANB + txt.BLACK + "Pressed:" + txt.RESET + txt.CYAN + txt.B + " " + self.keys_names[index] + txt.RESET)
                        self.press_MIDI_note(self.keys_midi_notes[index])
                        print("index: " + str(index))
                        print("midi value: " + str(self.keys_midi_notes[index]))
                    index += 1

                
            
    def press_MIDI_note(self, note): 
        # MIDI
        NOTE_ON = 0x90
        NOTE_OFF = 0x80

        note_on = [NOTE_ON, note, 112] # channel 1, note# (60 is middle C), velocity (112?)
        note_off = [NOTE_OFF, note, 0]
        self.midiout.send_message(note_on)
        #time.sleep(0.05)

        def send_off():
            self.midiout.send_message(note_off)

        threading.Timer(0.05, send_off).start()

        # make threads daemon to prevent blocking shutdown
        t = threading.Timer(0.1, send_off)
        t.daemon = True
        t.start()


    def toggle_sm(self):
        if self.sm_ON:
            #self.sm_ON = False
            print("\n" + self.SM_OFF_TXT + "#### " + self.SM_OFF_TXT_B + "SOUND MODE OFF" + self.SM_OFF_TXT + " ####\n" + txt.RESET)
        else:
            #self.sm_ON = True
            print("\n" + self.SM_ON_TXT +"#### " + self.SM_ON_TXT_B + "SOUND MODE ON" + self.SM_ON_TXT + " ####\n" + txt.RESET)
            
        self.sm_ON = (not self.sm_ON)


if __name__ == '__main__':
    vm = VirtualMIDI()


     
