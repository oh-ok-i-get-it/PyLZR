import midiKeyboard as midi

MODE_QUIET_CUTOFF = 1000
MODE1_CUTOFF = 7000
MODE2_CUTOFF = 12000


def setMode(amp_avg):
    if amp_avg < MODE_QUIET_CUTOFF:
        soundmode_mode = 0
    elif amp_avg < MODE1_CUTOFF:
        soundmode_mode = 1
    elif amp_avg < MODE2_CUTOFF:
        soundmode_mode = 2
    else:
        soundmode_mode = 3
    return soundmode_mode


def updateMode(soundmode_mode, midiout):
    if soundmode_mode == 0:
        midi.press_MIDI_note(midi.SPACE, midiout)
        print("\n>>>> SM: 0 SENT <<<<\n")
    elif soundmode_mode == 1:
        midi.press_MIDI_note(midi.ONE, midiout)
        print("\n>>>> SM: 1 SENT <<<<\n")
    elif soundmode_mode == 2:
        midi.press_MIDI_note(midi.TWO, midiout)
        print("\n>>>> SM: 2 SENT <<<<\n")
    else: 
        midi.press_MIDI_note(midi.THREE, midiout)
        print("\n>>>> SM: 3 SENT <<<<\n")


def draw_text(text, font, text_col):
    img = font.render(text, True, text_col)
    return img
def draw_text(text, font, text_col, x, y, screen):
    img = font.render(text, True, text_col)
    screen.blit(img, (x, y))
