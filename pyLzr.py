"""
Main file for PyLZR-

probably first going to start with building a audio spectrum analyzer/visualizer 
to read microphone input 
  then send MIDI signal to virtual MIDI device?
OR
  integrate virtual MIDI device to send MIDI signals based on audio visualizer
  values (effectively sound reactive mode)?
which will be connected to SoundSwitch until I can build or find a 
good DMX protocol API
 
AudioVisualizer -> virtual MIDI device/keyboard -> SoundSwitch -> DMX adapter -> laser
|_________________|
    PyLZR
OR
|__________________________________________________|
                    PyLZR

Note to self: decide to either bring over old PyLZR code from PyCharm or 
start from scratch on GUI (possibly better to restart because might not 
use OpenDMX or OLA - but maybe try OLA with ArtNet adapter?)

"""
import pyaudio
import math
import pygame


#### PYGAME variables
screen_width = 500
screen_height = 500
caption = "PyLZR Visualizer"
tick_rate = 60


### PYGAME initialization
#initialize all imported pygame modules
pygame.init()
#set display
pygame.display.set_caption(caption)
#variable to set up screen
screen = pygame.display.set_mode((screen_width, screen_height))
#variable to keep track of time
clock = pygame.time.Clock()


### PYAUDIO variables: audio initialization
CHUNK = 1024
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
MIN_SOUND_BOUND = 10

### PYAUDIO initialization
#assign variable to the pyaudio object
p = pyaudio.PyAudio()
#variable stream to create open audio stream
stream = p.open(format = FORMAT,
                channels = CHANNELS,
                rate = RATE,
                input = True,
                frames_per_buffer = CHUNK)


### METHODS
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


### PYGAME WINDOW
#CONSTANT VARIABLES
DAMPEN_AMP = 50
#running check bool variable
running = True
#set initial amplitude 
amplitude = 100
#cycle for pygame window
while running: 
    #for loop to handle any events
    for event in pygame.event.get():
        #capture if quit
        if event.type == pygame.QUIT:
            running = False
    
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

#shut down pygame window when finished
pygame.quit()



