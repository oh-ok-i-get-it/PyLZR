import numpy as np
import pyaudio as fake_pyaudio
import pytest

from pylzr.audio import AudioInput


def test_opens_default_device():
    audio = AudioInput()
    assert (audio.device_index, audio.device_name) == (0, 'Fake Mic')
    assert len(fake_pyaudio.streams) == 1


def test_switch_device_closes_old_stream():
    audio = AudioInput()
    pa = audio._pa
    old = fake_pyaudio.streams[-1]
    audio.switch_device(1)
    assert (audio.device_index, audio.device_name) == (1, 'Fake Line In')
    assert old.closed and not fake_pyaudio.streams[-1].closed
    assert audio._pa is pa and not pa.terminated       # PortAudio is not restarted


def test_failed_switch_keeps_current_device():
    received = []
    audio = AudioInput(on_chunk=lambda samples, overflowed: received.append(samples[0]))
    audio.start()
    current = fake_pyaudio.streams[-1]
    fake_pyaudio.fail_open.add(1)
    with pytest.raises(OSError):
        audio.switch_device(1)
    assert audio.device_name == 'Fake Mic' and not current.closed and audio.is_active
    fake_pyaudio.deliver(np.full(audio.chunk, 7, dtype=np.int16).tobytes())
    assert received == [7]                              # still capturing


def test_callback_passes_samples_and_overflow_flag():
    received = []
    audio = AudioInput(on_chunk=lambda samples, overflowed: received.append((samples, overflowed)))
    assert not audio.is_active                          # opened stopped; start() begins capture
    audio.start()
    fake_pyaudio.deliver(np.arange(audio.chunk, dtype=np.int16).tobytes())
    fake_pyaudio.deliver(np.zeros(audio.chunk, dtype=np.int16).tobytes(), overflow=True)
    (first, overflow1), (_, overflow2) = received
    assert first.dtype == np.int16 and first[5] == 5 and first.flags.writeable
    assert (overflow1, overflow2) == (False, True)


def test_switch_keeps_capturing_state():
    audio = AudioInput()
    audio.start()
    audio.switch_device(1)
    assert audio.is_active
    audio.stop()
    audio.switch_device(0)
    assert not audio.is_active


def test_failed_open_releases_portaudio():
    fake_pyaudio.fail_open.add(0)
    with pytest.raises(OSError):
        AudioInput()
    assert fake_pyaudio.instances[-1].terminated


def test_close():
    audio = AudioInput()
    audio.close()
    assert fake_pyaudio.streams[-1].closed and audio._pa.terminated


def test_refresh_finds_newly_plugged_in_device():
    audio = AudioInput(device_index=1)
    audio.start()
    fake_pyaudio.devices.append({'index': 3, 'name': 'USB Interface', 'maxInputChannels': 2})
    assert 'USB Interface' not in [name for _, name in audio.get_input_devices()]   # PortAudio's snapshot
    old_pa = audio._pa
    devices = audio.refresh_devices()
    assert (3, 'USB Interface') in devices
    assert old_pa.terminated and audio._pa is not old_pa
    assert audio.device_name == 'Fake Line In' and audio.is_active   # same device, still capturing


def test_refresh_falls_back_to_default_if_current_device_is_gone():
    audio = AudioInput(device_index=1)
    del fake_pyaudio.devices[1]                      # Fake Line In unplugged
    fake_pyaudio.devices[1]['index'] = 1             # keep indexes == positions
    audio.refresh_devices()
    assert audio.device_name == 'Fake Mic'


def test_failed_refresh_leaves_a_safe_object():
    audio = AudioInput()
    fake_pyaudio.fail_open.add(0)
    with pytest.raises(OSError):
        audio.refresh_devices()
    assert not audio.is_active
    audio.stop()
    audio.close()                                    # no crash without a stream


def test_open_by_name():
    assert AudioInput(device_name='Fake Line In').device_name == 'Fake Line In'
    assert AudioInput(device_name='Not Here').device_name == 'Fake Mic'
