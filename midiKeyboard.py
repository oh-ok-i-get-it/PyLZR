import pygame
import rtmidi
import time


#module constants
#KEY CONSTANTS
SPACE = 60
ONE = 61
TWO = 62
THREE = 63
FOUR = 64


#send midi note
def press_MIDI_note(note, midiout): 
    # MIDI
    NOTE_ON = 0x90
    NOTE_OFF = 0x80

    note_on = [NOTE_ON, note, 112] # channel 1, note# (60 is middle C), velocity (112?)
    note_off = [NOTE_OFF, note, 0]
    midiout.send_message(note_on)
    time.sleep(0.1)
    midiout.send_message(note_off)
    time.sleep(0.1)


#midi toggles soundmode
def toggle_soundmode(eventKey, soundmode_on):
    if eventKey == pygame.K_LSHIFT:
        if soundmode_on:
            soundmode_on = False
            print("SOUND MODE OFF")
        else:
            soundmode_on = True
            print("SOUND MODE ON")
    return soundmode_on


#midi keyboard
def keyboard(eventKey, midiout):
    if eventKey == pygame.K_SPACE:
        print("SPACE")
        press_MIDI_note(60, midiout)
    #KEYBOARD
    if eventKey == pygame.K_1:
        print("1")
        press_MIDI_note(61, midiout)
    if eventKey == pygame.K_2:
        print("2")
        press_MIDI_note(62, midiout)
    if eventKey == pygame.K_3:
        print("3")
        press_MIDI_note(63, midiout)
    if eventKey == pygame.K_4:
        print("4")
        press_MIDI_note(64, midiout)
    if eventKey == pygame.K_5:
        print("5")
        press_MIDI_note(65, midiout)
    if eventKey == pygame.K_6:
        print("6")
        press_MIDI_note(66, midiout)
    if eventKey == pygame.K_7:
        print("7")
        press_MIDI_note(67, midiout)
    if eventKey == pygame.K_8:
        print("8")
        press_MIDI_note(68, midiout)
    if eventKey == pygame.K_9:
        print("9")
        press_MIDI_note(69, midiout)
    if eventKey == pygame.K_0:
        print("0")
        press_MIDI_note(70, midiout)
    
    if eventKey == pygame.K_q:
        print("q")
        press_MIDI_note(71, midiout)
    if eventKey == pygame.K_w:
        print("w")
        press_MIDI_note(72, midiout)
    if eventKey == pygame.K_e:
        print("e")
        press_MIDI_note(73, midiout)
    if eventKey == pygame.K_r:
        print("r")
        press_MIDI_note(74, midiout)
    if eventKey == pygame.K_t:
        print("t")
        press_MIDI_note(75, midiout)
    if eventKey == pygame.K_y:
        print("y")
        press_MIDI_note(76, midiout)
    if eventKey == pygame.K_u:
        print("u")
        press_MIDI_note(77, midiout)
    if eventKey == pygame.K_i:
        print("i")
        press_MIDI_note(78, midiout)
    if eventKey == pygame.K_o:
        print("o")
        press_MIDI_note(79, midiout)
    if eventKey == pygame.K_p:
        print("p")
        press_MIDI_note(80, midiout)
    
    if eventKey == pygame.K_a:
        print("a")
        press_MIDI_note(81, midiout)
    if eventKey == pygame.K_s:
        print("s")
        press_MIDI_note(82, midiout)
    if eventKey == pygame.K_d:
        print("d")
        press_MIDI_note(83, midiout)
    if eventKey == pygame.K_f:
        print("f")
        press_MIDI_note(84, midiout)
    if eventKey == pygame.K_g:
        print("g")
        press_MIDI_note(85, midiout)
    if eventKey == pygame.K_h:
        print("h")
        press_MIDI_note(86, midiout)
    if eventKey == pygame.K_j:
        print("j")
        press_MIDI_note(87, midiout)
    if eventKey == pygame.K_k:
        print("k")
        press_MIDI_note(88, midiout)
    if eventKey == pygame.K_l:
        print("l")
        press_MIDI_note(89, midiout)
    if eventKey == pygame.K_SEMICOLON:
        print(";")
        press_MIDI_note(90, midiout)
    
    if eventKey == pygame.K_z:
        print("z")
        press_MIDI_note(91, midiout)
    if eventKey == pygame.K_x:
        print("x")
        press_MIDI_note(92, midiout)
    if eventKey == pygame.K_c:
        print("c")
        press_MIDI_note(93, midiout)
    if eventKey == pygame.K_v:
        print("v")
        press_MIDI_note(94, midiout)
    if eventKey == pygame.K_b:
        print("b")
        press_MIDI_note(95, midiout)
    if eventKey == pygame.K_n:
        print("n")
        press_MIDI_note(96, midiout)
    if eventKey == pygame.K_m:
        print("m")
        press_MIDI_note(97, midiout)
    if eventKey == pygame.K_COMMA:
        print(",")
        press_MIDI_note(98, midiout)
    if eventKey == pygame.K_PERIOD:
        print(".")
        press_MIDI_note(99, midiout)
    if eventKey == pygame.K_SLASH:
        print("/")
        press_MIDI_note(100, midiout)



