"""
PyLZR-

Combine audio visualizer and virtual midi for sound reactive mode

"""

import pyaudio
import math
import pygame
import rtmidi
import time

### CONSTANTS and Variables
# MIDI
NOTE_ON = 0x90
NOTE_OFF = 0x80

# PYGAME
screen_width = 500
screen_height = 500
caption = "PyLZR"
tick_rate = 60

# PYAUDIO
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
MIN_SOUND_BOUND = 10
DAMPEN_AMP = 5
amplitude = 100

### INITS
# PYAUDIO
#assign variable to the pyaudio object
p = pyaudio.PyAudio()
#variable stream to create open audio stream
stream = p.open(format = FORMAT,
                channels = CHANNELS,
                rate = RATE,
                input = True,
                frames_per_buffer = CHUNK)

# PYGAME
pygame.init()
#set display
pygame.display.set_caption(caption)
#variable to set up screen
screen = pygame.display.set_mode((screen_width, screen_height))
#variable to keep track of time
clock = pygame.time.Clock()

# MIDI
midiout = rtmidi.MidiOut()
available_ports = midiout.get_ports()

if available_ports:
    midiout.open_port(0)
else: 
    midiout.open_virtual_port("PyLZR-MIDI")


### METHODS
#method to send MIDI data that a note was pressed
def press_MIDI_note(note): 
    note_on = [NOTE_ON, note, 112] # channel 1, note# (60 is middle C), velocity (112?)
    note_off = [NOTE_OFF, note, 0]
    midiout.send_message(note_on)
    time.sleep(0.1)
    midiout.send_message(note_off)
    time.sleep(0.1)

#method to get microphone input level
def get_mic_input_level():
    #data variable to read audio; do not throw exception
    data = stream.read(CHUNK, exception_on_overflow = False)
    #variable "root mean squared"
    rms = 0
    #calculate rms (rms is average height of audio)
    for i in range(0, len(data), 2):
        sample = int.from_bytes(data[i: i + 2], byteorder = 'little', signed = True)
        rms += sample * sample
    rms = math.sqrt(rms / (CHUNK / 2))
    return rms

#method to draw sine wave from amplitude
def draw_sine_wave(amplitude):
    #fill screen color black
    screen.fill((0, 0, 0))
    #array to store plotted points within sine wave
    points = []
    #check minimum sound level to visualize audio
    if amplitude > MIN_SOUND_BOUND:
        #for loop for creating points for sound wave
        for x in range(screen_width): 
            y = screen_height / 2 + int(amplitude * math.sin(x * 0.02))
            points.append((x, y))
    #if not enough audio, draw flat line
    else: 
        points.append((0, screen_height / 2))
        points.append((screen_width, screen_height / 2))
    #draw points to screen
    pygame.draw.lines(screen, (255, 255, 255), False, points, 2)
    #"paint new line to screen"
    pygame.display.flip()


### RUNNING
with midiout:
    #variables 
    running = True

    #running
    while running == True:
        screen.fill(BLACK)

        for event in pygame.event.get():
            
            #CHECK CLOSE
            if event.type == pygame.QUIT:
                done = True



        #adjust and dampen amplitude height
        amplitude_adjustment = get_mic_input_level() / DAMPEN_AMP
        #set amplitude to steady low or take higher value (create min amp level)
        amplitude = max(MIN_SOUND_BOUND, amplitude_adjustment)

        #print rms for test
        print(get_mic_input_level())
        #draw sine wave
        draw_sine_wave(amplitude)
        #limit runs per second to 60
        clock.tick(tick_rate)



