"""
Virtual MIDI Device 
"""

import pygame   # <-- supports graphical environment
import mido     # <-|-- MIDI programming packages
import rtmidi   # <-|
import time

###METHODS
def press_MIDI_note(note): 
    note_on = [NOTE_ON, note, 112] # channel 1, note# (60 is middle C), velocity (112?)
    note_off = [NOTE_OFF, note, 0]
    midiout.send_message(note_on)
    time.sleep(0.1)
    midiout.send_message(note_off)
    time.sleep(0.1)


### PYGAME inits and variables
pygame.init()

BLACK = [0, 0, 0]
WHITE = [255, 255, 255]
SIZE = [380, 380]
screen = pygame.display.set_mode(SIZE)
pygame.display.set_caption("PyLZR MIDI")
clock = pygame.time.Clock()
done = False

### MIDI
#constants
NOTE_ON = 0x90
NOTE_OFF = 0x80

#init virtual midi
midiout = rtmidi.MidiOut()
available_ports = midiout.get_ports()

if available_ports:
    midiout.open_port(0)
else: 
    midiout.open_virtual_port("PyLZR-MIDI")


### running
#try-catch midiout object
with midiout: 

    #pygame running
    while done == False:
        screen.fill(BLACK)

        for event in pygame.event.get():

            #CHECK CLOSE
            if event.type == pygame.QUIT:
                done = True
            
            ### KEYBOARD INPUT
            if event.type == pygame.KEYDOWN:
                #SPACE BAR
                if event.key == pygame.K_SPACE:
                    print("SPACE")
                    press_MIDI_note(60)

                #KEYBOARD
                if event.key == pygame.K_1:
                    print("1")
                    press_MIDI_note(61)
                if event.key == pygame.K_2:
                    print("2")
                    press_MIDI_note(62)
                if event.key == pygame.K_3:
                    print("3")
                    press_MIDI_note(63)
                if event.key == pygame.K_4:
                    print("4")
                    press_MIDI_note(64)
                if event.key == pygame.K_5:
                    print("5")
                    press_MIDI_note(65)
                if event.key == pygame.K_6:
                    print("6")
                    press_MIDI_note(66)
                if event.key == pygame.K_7:
                    print("7")
                    press_MIDI_note(67)
                if event.key == pygame.K_8:
                    print("8")
                    press_MIDI_note(68)
                if event.key == pygame.K_9:
                    print("9")
                    press_MIDI_note(69)
                if event.key == pygame.K_0:
                    print("0")
                    press_MIDI_note(70)
                
                if event.key == pygame.K_q:
                    print("q")
                    press_MIDI_note(71)
                if event.key == pygame.K_w:
                    print("w")
                    press_MIDI_note(72)
                if event.key == pygame.K_e:
                    print("e")
                    press_MIDI_note(73)
                if event.key == pygame.K_r:
                    print("r")
                    press_MIDI_note(74)
                if event.key == pygame.K_t:
                    print("t")
                    press_MIDI_note(75)
                if event.key == pygame.K_y:
                    print("y")
                    press_MIDI_note(76)
                if event.key == pygame.K_u:
                    print("u")
                    press_MIDI_note(77)
                if event.key == pygame.K_i:
                    print("i")
                    press_MIDI_note(78)
                if event.key == pygame.K_o:
                    print("o")
                    press_MIDI_note(79)
                if event.key == pygame.K_p:
                    print("p")
                    press_MIDI_note(80)
                
                if event.key == pygame.K_a:
                    print("a")
                    press_MIDI_note(81)
                if event.key == pygame.K_s:
                    print("s")
                    press_MIDI_note(82)
                if event.key == pygame.K_d:
                    print("d")
                    press_MIDI_note(83)
                if event.key == pygame.K_f:
                    print("f")
                    press_MIDI_note(84)
                if event.key == pygame.K_g:
                    print("g")
                    press_MIDI_note(85)
                if event.key == pygame.K_h:
                    print("h")
                    press_MIDI_note(86)
                if event.key == pygame.K_j:
                    print("j")
                    press_MIDI_note(87)
                if event.key == pygame.K_k:
                    print("k")
                    press_MIDI_note(88)
                if event.key == pygame.K_l:
                    print("l")
                    press_MIDI_note(89)
                if event.key == pygame.K_SEMICOLON:
                    print(";")
                    press_MIDI_note(90)
                
                if event.key == pygame.K_z:
                    print("z")
                    press_MIDI_note(91)
                if event.key == pygame.K_x:
                    print("x")
                    press_MIDI_note(92)
                if event.key == pygame.K_c:
                    print("c")
                    press_MIDI_note(93)
                if event.key == pygame.K_v:
                    print("v")
                    press_MIDI_note(94)
                if event.key == pygame.K_b:
                    print("b")
                    press_MIDI_note(95)
                if event.key == pygame.K_n:
                    print("n")
                    press_MIDI_note(96)
                if event.key == pygame.K_m:
                    print("m")
                    press_MIDI_note(97)
                if event.key == pygame.K_COMMA:
                    print(",")
                    press_MIDI_note(98)
                if event.key == pygame.K_PERIOD:
                    print(".")
                    press_MIDI_note(99)
                if event.key == pygame.K_SLASH:
                    print("/")
                    press_MIDI_note(100)
                
            
del midiout


