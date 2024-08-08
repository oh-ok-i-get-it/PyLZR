import pyaudio
import time
import rtmidi
import math
import pygame
import midiKeyboard as midi
import audioAnalyzer as audio

### CONSTANTS and Variables
import pygame.display
# MIDI
NOTE_ON = 0x90
NOTE_OFF = 0x80

# PYGAME
screen_width = 500
screen_height = 500
caption = "PyLZR"
tick_rate = 60
BLACK = [0, 0, 0]
WHITE = [255, 255, 255]
BLUE = [0, 0, 128]
running = True

# PYAUDIO
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
MIN_SOUND_BOUND = 10
DAMPEN_AMP = 5
amplitude = 100

# AUDIO ANALYZER
MODE_QUIET_CUTOFF = 1000
MODE1_CUTOFF = 3000
MODE2_CUTOFF = 4500
AMP_BOOST = 10

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
#method to draw sine wave from amplitude
def draw_sine_wave(amplitude):
    #fill screen color black
    #screen.fill((0, 0, 0))
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

#method to add amplitude values over 1 second (60 runs)

#SOUNDMODE
soundmode_mode = -1


### RUNNING
with midiout:
    #variables 
    count = 0
    amp_count = 0
    amp_avg = 0
    sound_mode = False

    #KEY CONSTANTS
    SPACE = 60
    ONE = 61
    TWO = 62
    THREE = 63
    FOUR = 64

    #pygame text display
    font = pygame.font.Font("freesansbold.ttf", 32)

    #run
    while running:
        screen.fill(BLACK)

        #BUTTON/EVENT TRIGGERS
        for event in pygame.event.get():
            
            #CHECK CLOSE
            if event.type == pygame.QUIT:
                running = False

            #MODE SWITCH TOGGLING
            if event.type == pygame.KEYDOWN:
                sound_mode = midi.toggle_soundmode(event.key, sound_mode)

            if not sound_mode:
                ### KEYBOARD CONTROL
                if event.type == pygame.KEYDOWN:
                    midi.keyboard(event.key, midiout)
    

        #SOUND REACTIVE
        if sound_mode:
            soundmode_prev = soundmode_mode

            if amp_avg < MODE_QUIET_CUTOFF:
                soundmode_mode = 0
            if amp_avg < MODE1_CUTOFF:
                soundmode_mode = 1
            elif amp_avg < MODE2_CUTOFF:
                soundmode_mode = 2
            else:
                soundmode_mode = 3

            if soundmode_prev != soundmode_mode:
                if soundmode_mode == 0:
                    midi.press_MIDI_note(SPACE, midiout)
                    print("SM: 0 SENT")
                elif soundmode_mode == 1:
                    midi.press_MIDI_note(ONE, midiout)
                    print("SM: 1 SENT")
                elif soundmode_mode == 2:
                    midi.press_MIDI_note(TWO, midiout)
                    print("SM: 2 SENT")
                else: 
                    midi.press_MIDI_note(THREE, midiout)
                    print("SM: 3 SENT")

        #adjust and dampen amplitude height
        raw_amplitude = audio.get_mic_input_level(stream, CHUNK)
        amplitude_adjustment = raw_amplitude / DAMPEN_AMP
        #set amplitude to steady low or take higher value (create min amp level)
        amplitude = max(MIN_SOUND_BOUND, amplitude_adjustment)

        #print rms for test
        #print(get_mic_input_level())
        #draw sine wave
        draw_sine_wave(amplitude)
        #METHOD TO ADD UP AMPS FROM 60 frames and return average?
        if count == 30:
            amp_avg = amp_count / 30
            count = 0
            amp_count = 0
            font = pygame.font.Font("freesansbold.ttf", 32)
            text = font.render(str(amp_avg), True, BLUE, BLACK)
            textRect = text.get_rect()
            textRect.center = (screen_width // 2, screen_height // 2)
            screen.blit(text, textRect)
            print(amp_avg)
        else:
            amp_count += raw_amplitude * AMP_BOOST
        count += 1
        #display amp avg
        

        #limit runs per second to 60
        clock.tick(tick_rate)

del midiout


