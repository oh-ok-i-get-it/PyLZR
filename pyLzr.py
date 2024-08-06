"""
PyLZR-

Combine audio visualizer and virtual midi for sound reactive mode

TO DO:
-add mode to switch between sound reactive and keyboard control
-experiment with sound reactiveness (compute average amp per second, then set levels?)

"""

import pyaudio
import math
import pygame
import rtmidi
import time

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



### RUNNING
with midiout:
    #variables 
    count = 0
    amp_count = 0
    amp_avg = 0

    #pygame text display
    font = pygame.font.Font("freesansbold.ttf", 32)

    #run
    while running:
        screen.fill(BLACK)

        for event in pygame.event.get():
            
            #CHECK CLOSE
            if event.type == pygame.QUIT:
                running = False

            ### KEYBOARD CONTROL
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

        #adjust and dampen amplitude height
        amplitude_adjustment = get_mic_input_level() / DAMPEN_AMP
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
            amp_count += get_mic_input_level()
        count += 1
        #display amp avg
        

        #limit runs per second to 60
        clock.tick(tick_rate)

del midiout
