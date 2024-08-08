import pyaudio
import math
import pygame


#method to get microphone input level
def get_mic_input_level(stream, chunk):
    #data variable to read audio; do not throw exception
    data = stream.read(chunk, exception_on_overflow = False)
    #variable "root mean squared"
    rms = 0
    #calculate rms (rms is average height of audio)
    for i in range(0, len(data), 2):
        sample = int.from_bytes(data[i: i + 2], byteorder = 'little', signed = True)
        rms += sample * sample
    rms = math.sqrt(rms / (chunk / 2))
    return rms


#draw sine wave visualizer
def draw_sine_wave(amplitude, screen, MIN_SOUND_BOUND, screen_width, screen_height):
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

