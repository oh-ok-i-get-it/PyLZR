import pyaudio
import math


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



