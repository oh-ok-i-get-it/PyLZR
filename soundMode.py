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
        print("SM: 0 SENT")
    elif soundmode_mode == 1:
        midi.press_MIDI_note(midi.ONE, midiout)
        print("SM: 1 SENT")
    elif soundmode_mode == 2:
        midi.press_MIDI_note(midi.TWO, midiout)
        print("SM: 2 SENT")
    else: 
        midi.press_MIDI_note(midi.THREE, midiout)
        print("SM: 3 SENT")
