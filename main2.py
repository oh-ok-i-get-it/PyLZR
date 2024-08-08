import midiKeyboard2 as midi
import keyboard

running = True

while running:
    running = midi.keyboard_quit()

    midi.keyboard()