"""End-to-end golden test: fixed synthetic audio through the real main window.

Records every FFT frame (band sums), every LOW/HIGH average and every MIDI
Note ON (each with a matching Note OFF), and compares them with
tests/golden/pipeline.json. Refactors that
shouldn't change behaviour must reproduce this exactly.

If a change is MEANT to alter the output (e.g. a different FFT), regenerate
the file and review its diff:

    PYLZR_UPDATE_GOLDEN=1 pytest tests/test_pipeline_golden.py
"""

import json
import os
from pathlib import Path

import numpy as np
import pytest
import rtmidi as fake_rtmidi
from PyQt5.QtCore import Qt

from helpers import note_ons, tone_chunks, wait_for_note_offs

GOLDEN = Path(__file__).parent / 'golden' / 'pipeline.json'
W = 20   # chunks per averaging window at the default rate

# Note ONs the scenario must produce (dual mode is on: +15 except SPACE=106)
EXPECTED_NOTES = [
    106,   # silence             -> LOW 0 / HIGH 0 (SPACE)
    78,    # 80 Hz quiet         -> 1 / 0
    82,    # 80 Hz louder        -> 2 / 0
    77,    # 8 kHz               -> 0 / 3
    89,    # both                -> 3 / 3   (repeat window sends nothing)
    73,    # 'q' pressed with sound mode off
    82,    # quiet low, gain x2  -> 2 / 0
    78,    # Hann window         -> 1 / 0
    89,    # Hann, both loud     -> 3 / 3
    106,   # 10-chunk window of silence
]


def run_scenario(h):
    w = h.window
    h.key(Qt.Key_Shift)                                    # sound mode ON
    h.feed(tone_chunks(W))
    h.feed(tone_chunks(W, (80, 200)))
    h.feed(tone_chunks(W, (80, 400)))
    h.feed(tone_chunks(W, (8000, 2000)))
    h.feed(tone_chunks(W, (80, 800), (8000, 2000)))
    h.feed(tone_chunks(W, (80, 800), (8000, 2000)))        # unchanged: no note
    h.key(Qt.Key_Shift)                                    # sound mode OFF
    h.feed(tone_chunks(W))                                 # analysed, no note
    h.key(Qt.Key_Q)
    w.settings_panel.audio_gain_changed.emit(2.0)
    h.key(Qt.Key_Shift)                                    # sound mode ON
    h.feed(tone_chunks(W, (80, 200)))
    w.settings_panel.audio_gain_changed.emit(1.0)
    w.settings_panel.fft_window_changed.emit('hann')
    h.feed(tone_chunks(W, (80, 400)))
    h.feed(tone_chunks(W, (80, 2000), (8000, 20000)))
    w.controls.count_rate_changed.emit(10)
    h.feed(tone_chunks(10))
    wait_for_note_offs()


def test_pipeline_matches_golden(os_name, make_window):
    if os_name == 'win':
        fake_rtmidi.ports.append('PyLZR-MIDI 1')     # loopMIDI running
    h = make_window()
    run_scenario(h)

    result = {
        'frames':   [list(f) for f in h.frames],
        'averages': [list(a) for a in h.averages],
        'note_ons': note_ons(),
    }

    if os.environ.get('PYLZR_UPDATE_GOLDEN'):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(json.dumps(result, indent=1) + '\n')
        pytest.skip(f'golden file updated: {GOLDEN}')

    golden = json.loads(GOLDEN.read_text())

    # Human-readable expectations first, so a failure says what changed
    assert [note for note, _ in result['note_ons']] == EXPECTED_NOTES
    expected_port = 'PyLZR-MIDI 1' if os_name == 'win' else 'PyLZR-MIDI'
    assert {port for port, _ in fake_rtmidi.sent} == {expected_port}

    assert result['note_ons'] == golden['note_ons']
    assert len(result['frames']) == len(golden['frames'])
    assert len(result['averages']) == len(golden['averages'])
    # float32 FFT: allow tiny differences between platforms / numpy versions
    np.testing.assert_allclose(result['frames'], golden['frames'], rtol=1e-5, atol=1e-6)
    np.testing.assert_allclose(result['averages'], golden['averages'], rtol=1e-5, atol=1e-6)


def test_smoothing_does_not_affect_analysis(make_window):
    """Display smoothing must never change the averages or MIDI output."""
    audio = [tone_chunks(W, (80, 400)), tone_chunks(W, (8000, 2000))]

    plain = make_window()
    plain.key(Qt.Key_Shift)
    for chunks in audio:
        plain.feed(chunks)
    wait_for_note_offs()
    plain_notes = note_ons()
    fake_rtmidi.sent.clear()

    smoothed = make_window()
    smoothed.window.settings_panel.smoothing_changed.emit(0.9)
    smoothed.key(Qt.Key_Shift)
    for chunks in audio:
        smoothed.feed(chunks)
    wait_for_note_offs()

    np.testing.assert_allclose(smoothed.averages, plain.averages, rtol=1e-6)
    assert note_ons() == plain_notes
