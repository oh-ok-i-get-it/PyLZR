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
    audio = AudioInput()
    current = fake_pyaudio.streams[-1]
    fake_pyaudio.fail_open.add(1)
    with pytest.raises(OSError):
        audio.switch_device(1)
    assert audio.device_name == 'Fake Mic' and not current.closed
    fake_pyaudio.queue.append(np.full(audio.chunk, 7, dtype=np.int16).tobytes())
    assert audio.read_chunk()[0] == 7                   # still reading


def test_failed_open_releases_portaudio(monkeypatch):
    created = []
    real = fake_pyaudio.PyAudio
    monkeypatch.setattr(fake_pyaudio, 'PyAudio', lambda: created.append(real()) or created[-1])
    fake_pyaudio.fail_open.add(0)
    with pytest.raises(OSError):
        AudioInput()
    assert created[0].terminated


def test_close():
    audio = AudioInput()
    audio.close()
    assert fake_pyaudio.streams[-1].closed and audio._pa.terminated
