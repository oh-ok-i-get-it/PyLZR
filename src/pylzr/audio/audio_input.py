import pyaudio
import numpy as np

class AudioInput:
    def __init__(self, chunk_size=2048, rate=44100):
        self.chunk_size = chunk_size
        self.rate = rate
        self.p = pyaudio.PyAudio()
        self.stream = self.p.open(format=pyaudio.paInt16,
                                  channels=1, rate=rate,
                                  input=True, frames_per_buffer=chunk_size)

    def get_audio_chunk(self):
        raw = self.stream.read(self.chunk_size, exception_on_overflow=False)
        return np.frombuffer(raw, dtype=np.int16)

    def close(self):
        self.stream.stop_stream()
        self.stream.close()
        self.p.terminate()

        