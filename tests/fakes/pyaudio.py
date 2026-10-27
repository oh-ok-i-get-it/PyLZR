"""In-memory stand-in for PyAudio 0.2.x used by the test suite.

Audio is served from `queue` (bytes of int16 samples, one chunk per read);
when the queue is empty, reads return silence. Opening a device index listed
in `fail_open` raises, to simulate an unusable device.
"""

from collections import deque

paInt16 = 8

devices   = []      # device info dicts, index == position
queue     = deque()
fail_open = set()
streams   = []      # every stream opened, for lifecycle checks


def reset():
    devices[:] = [
        {'index': 0, 'name': 'Fake Mic',      'maxInputChannels': 1},
        {'index': 1, 'name': 'Fake Line In',  'maxInputChannels': 2},
        {'index': 2, 'name': 'Fake Speakers', 'maxInputChannels': 0},
    ]
    queue.clear()
    fail_open.clear()
    streams.clear()


reset()


class _Stream:
    def __init__(self, device_index: int, frames_per_buffer: int):
        self.device_index = device_index
        self._frames = frames_per_buffer
        self.closed = False

    def read(self, num_frames, exception_on_overflow=True):
        if queue:
            return queue.popleft()
        return bytes(2 * num_frames)

    def stop_stream(self):
        pass

    def close(self):
        self.closed = True


class PyAudio:
    def __init__(self):
        self.terminated = False

    def get_default_input_device_info(self):
        return devices[0]

    def get_device_info_by_index(self, index):
        if not 0 <= index < len(devices):
            raise OSError(-9996, 'Invalid device index')
        return devices[index]

    def get_device_count(self):
        return len(devices)

    def open(self, *, input_device_index=None, frames_per_buffer=1024, **_):
        if input_device_index in fail_open:
            raise OSError(-9985, 'Device unavailable')
        stream = _Stream(input_device_index, frames_per_buffer)
        streams.append(stream)
        return stream

    def terminate(self):
        self.terminated = True
