from collections.abc import Callable

import pyaudio
import numpy as np
from ..core import CHUNK, SAMPLE_RATE
from ..core.app_logger import get_logger

log = get_logger('audio')

# on_chunk(samples, overflowed): called on PortAudio's audio thread
ChunkHandler = Callable[[np.ndarray, bool], None]


class AudioInput:
    """Manages the PyAudio capture stream (callback mode).

    PortAudio calls back on its own audio thread with each chunk of int16
    samples; they are passed to `on_chunk(samples, overflowed)`, where
    `overflowed` means input was lost before this chunk because it wasn't
    collected in time. Keep on_chunk short — hand the data to another thread.

    Owns one PyAudio (PortAudio) instance for its lifetime. Call start() /
    stop() to control capture, switch_device() to change input, and close()
    on shutdown. Pass device_index or device_name to open a specific input
    device; otherwise (or if the name isn't found) the system default is used.
    get_input_devices() enumerates inputs for the UI.
    """

    def __init__(self, chunk: int = CHUNK, rate: int = SAMPLE_RATE,
                 device_index: int | None = None, on_chunk: ChunkHandler | None = None,
                 device_name: str | None = None):
        self.chunk = chunk
        self.rate  = rate
        self._on_chunk = on_chunk or (lambda samples, overflowed: None)

        self._pa = pyaudio.PyAudio()
        self._stream = None
        if device_index is None and device_name:
            device_index = self.find_device(device_name)
        try:
            self._open(device_index, start=False)
        except Exception:
            self._pa.terminate()
            raise

    def find_device(self, name: str) -> int | None:
        """Index of the input device called `name`, or None."""
        return next((idx for idx, dev in self.get_input_devices() if dev == name), None)

    def _open(self, device_index: int | None, start: bool):
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
            stream_callback=self._on_audio,
            start=start,
        )
        previous = self._stream
        self._stream, self.device_index, self.device_name = stream, index, name
        log.info(f'Audio: opened "{name}" (chunk={self.chunk}, rate={self.rate}Hz)')
        return previous

    def _on_audio(self, in_data, frame_count, time_info, status):
        # PortAudio's audio thread
        samples = np.frombuffer(in_data, dtype=np.int16).copy()
        self._on_chunk(samples, bool(status & pyaudio.paInputOverflow))
        return None, pyaudio.paContinue

    # A failed rescan can leave no stream open; these then do nothing.

    @property
    def is_active(self) -> bool:
        return self._stream is not None and self._stream.is_active()

    def start(self):
        if self._stream is not None:
            self._stream.start_stream()

    def stop(self):
        if self._stream is not None:
            self._stream.stop_stream()

    def switch_device(self, device_index: int):
        """Switch input to device_index, capturing if the old one was. If it
        can't be opened the current device stays open and the error is raised."""
        old_name = self.device_name
        previous = self._open(device_index, start=self.is_active)
        self._close_stream(previous, old_name)

    def refresh_devices(self) -> list[tuple[int, str]]:
        """Restart PortAudio so inputs plugged in since startup appear (it only
        lists devices when it starts). Reopens the current device by name, or
        the system default if it's gone; capture pauses briefly. Returns the
        new device list."""
        was_active, name = self.is_active, self.device_name
        self._close_stream(self._stream, name)
        self._pa.terminate()
        self._pa = pyaudio.PyAudio()
        self._stream = None
        index = self.find_device(name)
        try:
            self._open(index, start=was_active)
        except Exception:
            if index is None:
                raise                       # the default itself failed: no input
            self._open(None, start=was_active)
        devices = self.get_input_devices()
        log.info(f'Audio: rescanned inputs ({len(devices)} found)')
        return devices

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

    @staticmethod
    def _close_stream(stream, name: str):
        stream.stop_stream()
        stream.close()
        log.info(f'Audio: stream closed ("{name}")')

    def close(self):
        if self._stream is not None:
            self._close_stream(self._stream, self.device_name)
            self._stream = None
        self._pa.terminate()
