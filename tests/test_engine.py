"""AudioEngine used on its own, without any window."""

import threading

import numpy as np
import pyaudio as fake_pyaudio
import pytest
from PyQt5.QtCore import Qt

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
    eng.spectrum_ready.connect(eng.frames.append)
    eng.averages_ready.connect(lambda lo, hi: eng.averages.append((lo, hi)))
    eng.level_measured.connect(lambda peak, clip: eng.levels.append((peak, clip)))
    eng.diagnostics = []
    eng.diagnostics_updated.connect(lambda fps, overflows: eng.diagnostics.append((fps, overflows)))
    eng.start()
    yield eng
    eng.shutdown()


def feed(engine, chunks, overflow=False):
    target = len(engine.frames) + len(chunks)
    for chunk in chunks:
        fake_pyaudio.deliver(chunk.tobytes(), overflow=overflow)
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
    assert engine.switch_device(1) is False
    assert engine.audio.device_name == 'Fake Mic'
    assert engine.audio.is_active
    engine.stop()
    assert engine.switch_device(0) is True
    assert not engine.audio.is_active               # stays stopped if it was stopped


def test_stop_and_start(engine):
    engine.stop()
    assert not engine.audio.is_active
    engine.start()
    feed(engine, tone_chunks(1, (440, 1000)))
    assert len(engine.frames) == 1


def test_overflows_are_counted_and_reported(engine, caplog):
    feed(engine, tone_chunks(3, (440, 1000)), overflow=True)
    feed(engine, tone_chunks(2, (440, 1000)))
    with caplog.at_level('WARNING', logger='pylzr'):
        engine._report_diagnostics()             # the 1 s diagnostics tick
        engine._report_diagnostics()
    assert [fps_overflows[1] for fps_overflows in engine.diagnostics] == [3, 3]   # running total
    warnings = [r.getMessage() for r in caplog.records if r.levelname == 'WARNING']
    assert warnings == ['Audio input overflowed 3× in the last second']           # once, not every tick


def test_chunks_from_the_audio_thread_are_processed_in_order(engine):
    """PortAudio calls back on its own thread; processing must stay ordered
    and happen on the engine's thread."""
    engine.measure_level = True
    amplitudes = [1000 * (i + 1) for i in range(10)]
    threads = set()
    # DirectConnection: record the thread that actually emits (i.e. that processed the chunk)
    engine.level_measured.connect(lambda *_: threads.add(threading.get_ident()), Qt.DirectConnection)

    def audio_thread():
        for amp in amplitudes:
            fake_pyaudio.deliver(np.full(engine.audio.chunk, amp, dtype=np.int16).tobytes())

    worker = threading.Thread(target=audio_thread)
    worker.start()
    worker.join()
    wait_until(lambda: len(engine.levels) == len(amplitudes))
    assert [round(peak * 32767) for peak, _ in engine.levels] == amplitudes
    assert threads == {threading.get_ident()}       # processed on this (GUI) thread, not the audio thread


def test_shutdown_stops_everything_and_is_idempotent(engine):
    engine.shutdown()
    assert fake_pyaudio.streams[-1].closed
    assert engine.fft_thread.isFinished()
    engine.shutdown()      # second call is a no-op (the fixture calls it again too)


def test_turning_sound_mode_on_sends_current_cue_at_once(engine):
    feed(engine, tone_chunks(20, (80, 400)))          # analysed while off: LOW 2 / HIGH 0
    assert engine.output.notes == []
    engine.set_sound_mode(True)
    assert engine.output.notes == [82]                # no need to wait for the next window
    engine.set_sound_mode(False)
    engine.set_sound_mode(True)
    assert engine.output.notes == [82, 82]            # re-sent even though the mode is unchanged


def test_turning_sound_mode_on_before_any_audio_sends_nothing(engine):
    engine.set_sound_mode(True)
    assert engine.output.notes == []
