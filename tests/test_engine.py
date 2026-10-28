"""AudioEngine used on its own, without any window."""

import pyaudio as fake_pyaudio
import pytest

from pylzr.engine import AudioEngine

from helpers import tone_chunks, wait_until


class RecordingOutput:
    def __init__(self):
        self.notes = []

    def press_note(self, note):
        self.notes.append(note)


@pytest.fixture
def engine(qapp):
    output = RecordingOutput()
    eng = AudioEngine(output)
    eng.output = output                     # for the tests' convenience
    eng.frames, eng.averages, eng.levels = [], [], []
    eng.spectrum_ready.connect(lambda *bands: eng.frames.append(bands))
    eng.averages_ready.connect(lambda lo, hi: eng.averages.append((lo, hi)))
    eng.level_measured.connect(lambda peak, clip: eng.levels.append((peak, clip)))
    yield eng
    eng.shutdown()


def feed(engine, chunks):
    target = len(engine.frames) + len(chunks)
    for chunk in chunks:
        fake_pyaudio.queue.append(chunk.tobytes())
        engine.tick()
    wait_until(lambda: len(engine.frames) >= target)


def test_runs_without_a_gui_and_sends_notes(engine):
    engine.set_sound_mode(True)
    feed(engine, tone_chunks(20, (80, 400)))
    assert len(engine.averages) == 1
    assert engine.output.notes == [82]       # LOW 2 / HIGH 0, dual mode on


def test_no_notes_while_sound_mode_off(engine):
    feed(engine, tone_chunks(20, (80, 400)))
    assert len(engine.averages) == 1 and engine.output.notes == []


def test_toggle_sound_mode(engine):
    assert engine.toggle_sound_mode() is True
    assert engine.toggle_sound_mode() is False


@pytest.mark.parametrize('count_rate, windows', [(20, 120), (10, 240), (30, 80), (35, 69), (50, 48)])
def test_dual_mode_period_stays_about_2400_frames(engine, count_rate, windows):
    engine.set_count_rate(count_rate)
    assert engine.analyzer.count_rate == count_rate
    assert engine.sound_mode.dm_countdown == windows


def test_level_measured_only_when_requested(engine):
    feed(engine, tone_chunks(1, (440, 16384)))
    assert engine.levels == []
    engine.measure_level = True
    feed(engine, tone_chunks(1, (440, 32767)))
    peak, clipping = engine.levels[0]
    assert peak > 0.99 and clipping


def test_gain_scales_input(engine):
    engine.measure_level = True
    engine.set_gain(2.0)
    feed(engine, tone_chunks(1, (440, 8000)))
    assert engine.levels[0][0] == pytest.approx(16000 / 32767, rel=1e-3)


def test_failed_device_switch_keeps_running(engine):
    fake_pyaudio.fail_open.add(1)
    engine.start()
    assert engine.switch_device(1) is False
    assert engine.audio.device_name == 'Fake Mic'
    assert engine._capture_timer.isActive()
    engine.stop()
    assert engine.switch_device(0) is True
    assert not engine._capture_timer.isActive()     # stays stopped if it was stopped


def test_shutdown_stops_everything_and_is_idempotent(engine):
    engine.start()
    engine.shutdown()
    assert fake_pyaudio.streams[-1].closed
    assert engine.fft_thread.isFinished()
    assert not engine._capture_timer.isActive()
    engine.shutdown()      # second call is a no-op (the fixture calls it again too)
