import pyaudio
import numpy as np
from ..core import CHUNK, SAMPLE_RATE
from ..core.app_logger import get_logger

log = get_logger('audio')


class AudioInput:
    """Manages the PyAudio capture stream.

    Owns one PyAudio (PortAudio) instance for its lifetime. Call read_chunk()
    each frame, switch_device() to change input, and close() on shutdown.

    Pass device_index to open a specific input device; None uses the system
    default. get_input_devices() enumerates available inputs for the UI.
    """

    def __init__(self, chunk: int = CHUNK, rate: int = SAMPLE_RATE,
                 device_index: int | None = None):
        self.chunk = chunk
        self.rate  = rate
        self.timer_interval_ms = int(chunk / rate * 1000)

        self._pa = pyaudio.PyAudio()
        self._stream = None
        try:
            self._open(device_index)
        except Exception:
            self._pa.terminate()
            raise

    def _open(self, device_index: int | None):
        """Open a stream on device_index and make it current. Returns the
        previous stream (or None). On failure nothing changes and it raises."""
        try:
            dev_info = (
                self._pa.get_default_input_device_info()
                if device_index is None
                else self._pa.get_device_info_by_index(device_index)
            )
            index = int(dev_info['index'])
            name  = dev_info['name']
        except Exception:
            index = device_index
            name  = 'Unknown'

        stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.chunk,
            input_device_index=index,
        )
        previous = self._stream
        self._stream, self.device_index, self.device_name = stream, index, name
        log.info(f'Audio: opened "{name}" (chunk={self.chunk}, rate={self.rate}Hz)')
        return previous

    def switch_device(self, device_index: int):
        """Switch input to device_index. If it can't be opened the current
        device stays open and the error is raised."""
        old_name = self.device_name
        previous = self._open(device_index)
        self._close_stream(previous, old_name)

    def get_input_devices(self) -> list[tuple[int, str]]:
        """Return (index, name) for every available input device."""
        devices = []
        for i in range(self._pa.get_device_count()):
            try:
                info = self._pa.get_device_info_by_index(i)
                if info.get('maxInputChannels', 0) > 0:
                    devices.append((int(info['index']), info['name']))
            except Exception:
                pass
        return devices

    def read_chunk(self) -> np.ndarray:
        """Read one chunk from the hardware stream. Returns int16 array."""
        raw = self._stream.read(self.chunk, exception_on_overflow=False)
        return np.frombuffer(raw, dtype=np.int16)

    @staticmethod
    def _close_stream(stream, name: str):
        stream.stop_stream()
        stream.close()
        log.info(f'Audio: stream closed ("{name}")')

    def close(self):
        self._close_stream(self._stream, self.device_name)
        self._pa.terminate()
