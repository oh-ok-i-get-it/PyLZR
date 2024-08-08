import pyaudio
import struct
import numpy as np
import matplotlib.pyplot as plt



#variables
CHUNK = 1024 * 4
FORMAT =  pyaudio.paInt16
CHANNELS = 1
RATE = 44100

#pyaudio class instance
p = pyaudio.PyAudio()
#create stream object
stream = p.open(format = FORMAT,
                channels = CHANNELS,
                rate = RATE,
                input = True,
                frames_per_buffer = CHUNK)

#create data stream object
data = stream.read(CHUNK)
#unpack data stream
#data_int = struct.unpack(str(2 * CHUNK) + 'B', data)
data_int = np.array(struct.unpack(str(CHUNK) + 'h', data))[::16] + 127

#plot data
fig, ax = plt.subplots()
ax.plot(data_int, '-')
plt.show()


