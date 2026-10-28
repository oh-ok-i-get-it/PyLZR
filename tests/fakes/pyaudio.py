"""In-memory stand-in for PyAudio 0.2.x used by the test suite.

Streams run in callback mode like the real library. Nothing is captured on
its own: tests call deliver() to hand one chunk to the active stream's
callback (as PortAudio would from its audio thread). Opening a device index
listed in `fail_open` raises, to simulate an unusable device.

Like real PortAudio, each PyAudio() instance only sees the devices that
existed when it was created; add to `devices` and create a new instance (as
AudioInput.refresh_devices() does) to see a newly plugged-in device.
"""

paInt16 = 8
paContinue = 0
paInputOverflow = 2

devices   = []      # device info dicts, index == position
fail_open = set()
streams   = []      # every stream opened, for lifecycle checks
instances = []      # every PyAudio() created


def reset():
    devices[:] = [
        {'index': 0, 'name': 'Fake Mic',      'maxInputChannels': 1},
        {'index': 1, 'name': 'Fake Line In',  'maxInputChannels': 2},
        {'index': 2, 'name': 'Fake Speakers', 'maxInputChannels': 0},
    ]
    fail_open.clear()
    streams.clear()
    instances.clear()


reset()


def deliver(data: bytes, overflow: bool = False, stream=None):
    """Pass one chunk to `stream`'s callback (default: the only active stream)."""
    if stream is None:
        active = [s for s in streams if s.active]
        assert len(active) == 1, f'expected one active stream, found {len(active)}'
        stream = active[0]
    assert stream.active, 'stream is not capturing'
    stream.deliver(data, overflow)


class _Stream:
    def __init__(self, device_index, frames_per_buffer, callback, start):
        self.device_index = device_index
        self._frames = frames_per_buffer
        self._callback = callback
        self.active = start
        self.closed = False

    def deliver(self, data: bytes, overflow: bool):
        status = paInputOverflow if overflow else 0
        self._callback(data, self._frames, {}, status)

    def start_stream(self):
        self.active = True

    def stop_stream(self):
        self.active = False

    def is_active(self):
        return self.active

    def close(self):
        self.active = False
        self.closed = True


class PyAudio:
    def __init__(self):
        self.terminated = False
        self._devices = list(devices)      # enumerated once, at initialisation
        instances.append(self)

    def get_default_input_device_info(self):
        return self._devices[0]

    def get_device_info_by_index(self, index):
        if not 0 <= index < len(self._devices):
            raise OSError(-9996, 'Invalid device index')
        return self._devices[index]

    def get_device_count(self):
        return len(self._devices)

    def open(self, *, input_device_index=None, frames_per_buffer=1024,
             stream_callback=None, start=True, **_):
        if input_device_index in fail_open:
            raise OSError(-9985, 'Device unavailable')
        stream = _Stream(input_device_index, frames_per_buffer, stream_callback, start)
        streams.append(stream)
        return stream

    def terminate(self):
        self.terminated = True
