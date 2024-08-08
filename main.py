import pyaudio
import time
import rtmidi
import math
import pygame
import midiKeyboard as midi
import audioAnalyzer as audio
import soundMode as sm

### CONSTANTS and Variables ###################################################################
import pygame.display
# MIDI
NOTE_ON = 0x90
NOTE_OFF = 0x80

# PYGAME
screen_width = 500
screen_height = 500
caption = "PyLZR"
TICK_RATE = 60 #tick rate
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
MODE1_CUTOFF = 7000
MODE2_CUTOFF = 12000
AMP_BOOST = 10
SM_TICK_RATE = 15 #ticks over which to update avg amp

#############################################################################################




### INITS ###################################################################################
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

#SOUNDMODE
soundmode_mode = -1

#################################################################################################




### RUNNING: VIRTUAL MIDI <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
with midiout:
    #variables 
    count = 0
    amp_count = 0
    amp_avg = 0
    sound_mode = False

    #pygame text display
    font = pygame.font.Font("freesansbold.ttf", 32)

    ### RUNNING LOOP ############################################################################
    while running:
        screen.fill(BLACK)

        ### BUTTON/EVENT TRIGGERS ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
        for event in pygame.event.get():
            
            # CHECK CLOSE
            if event.type == pygame.QUIT:
                running = False

            # MODE SWITCH TOGGLING
            if event.type == pygame.KEYDOWN:
                sound_mode = midi.toggle_soundmode(event.key, sound_mode)

            # KEYBOARD MODE ------------------------------------------------------------
            if not sound_mode:
                if event.type == pygame.KEYDOWN:
                    midi.keyboard(event.key, midiout)
            # --------------------------------------------------------------------------

        # ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~


        # SOUND REACTIVE ---------------------------------------------------------------
        if sound_mode:

            soundmode_prev = soundmode_mode

            soundmode_mode = sm.setMode(amp_avg)

            if soundmode_prev != soundmode_mode:
                sm.updateMode(soundmode_mode, midiout)
        # ------------------------------------------------------------------------------



        # LIVE AUDIO ANALYSIS ----------------------------------------------------------
        raw_amplitude = audio.get_mic_input_level(stream, CHUNK)

        amplitude_adjustment = raw_amplitude / DAMPEN_AMP

        #set amplitude to steady low or take higher value (create min amp level)
        amplitude = max(MIN_SOUND_BOUND, amplitude_adjustment)

        #draw sine wave
        audio.draw_sine_wave(amplitude, screen, MIN_SOUND_BOUND, screen_width, screen_height)

        #calc and output amp avg every # of ticks !!!!!!!MOVE TO SM MODULE?????
        if count == SM_TICK_RATE:
            amp_avg = amp_count / SM_TICK_RATE 
            count = 0
            amp_count = 0
            font = pygame.font.Font("freesansbold.ttf", 32)
            text = font.render(str(amp_avg), True, BLUE, BLACK)
            textRect = text.get_rect()
            textRect.center = (screen_width // 2, screen_height // 2)
            screen.blit(text, textRect)
            print(int(amp_avg))
        else:
            amp_count += raw_amplitude * AMP_BOOST
        count += 1
        # -------------------------------------------------------------------------------

        #limit runs per second to 60
        clock.tick(TICK_RATE)
    ##############################################################################################

del midiout

# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

