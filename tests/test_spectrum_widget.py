from itertools import pairwise

import numpy as np
import pytest

from pylzr.analysis import BandLayout
from pylzr.gui import SpectrumWidget


@pytest.fixture
def widget(qapp):
    return SpectrumWidget(BandLayout(2048, 44100))


def shown(widget):
    """Y data given to the low, mid, high, top lines (before log scaling)."""
    return [line.getOriginalDataset()[1] for line in widget._spectrum_lines]


def spectrum(value):
    return np.full(2048 // 2 + 1, value)


def test_draws_every_bin_but_dc_against_its_frequency(widget):
    """Each band line after the first also starts at the previous band's last
    bin (so the drawn line has no gaps); without those shared points the
    lines are exactly bins 1..1024. (Gentle smoothing off: it would change
    the values.)"""
    widget = SpectrumWidget(BandLayout(2048, 44100), gentle=False)
    widget.update_spectrum(np.arange(1025, dtype=float))
    xs = [line.getOriginalDataset()[0] for line in widget._spectrum_lines]
    ys = shown(widget)
    for previous, line in pairwise(ys):
        assert line[0] == previous[-1]

    def own(parts):            # each line without the point it shares with the one before
        return np.concatenate([parts[0], *(p[1:] for p in parts[1:])])

    np.testing.assert_array_equal(own(ys), np.arange(1, 1025))
    np.testing.assert_allclose(own(xs), np.arange(1, 1025) * 44100 / 2048)


def test_without_smoothing_shows_raw_bands(widget):
    widget.update_spectrum(spectrum(1.0))
    widget.update_spectrum(spectrum(3.0))
    assert all(np.allclose(y, 3.0) for y in shown(widget))


def test_smoothing_is_an_ema_of_displayed_bands(widget):
    widget.set_smoothing(0.75)
    widget.update_spectrum(spectrum(1.0))     # first frame seeds the average
    widget.update_spectrum(spectrum(3.0))
    assert all(np.allclose(y, 1.5) for y in shown(widget))   # 0.75*previous + 0.25*new


def test_turning_smoothing_off_resets_it(widget):
    widget.set_smoothing(0.5)
    widget.update_spectrum(spectrum(1.0))
    widget.set_smoothing(0.0)
    widget.set_smoothing(0.5)
    widget.update_spectrum(spectrum(3.0))     # starts fresh, not averaged with 1.0
    assert all(np.allclose(y, 3.0) for y in shown(widget))


def test_waveform_is_scaled_to_0_255(widget):
    chunk = np.array([-32768, 0, 32767] + [0] * 2045, dtype=np.int16)
    widget.update_waveform(chunk)
    x, y = widget._waveform_line.getData()
    assert list(y[:3]) == [0, 128, 255] and len(x) == 2048


def tick_labels(plot, name):
    return [label for _value, label in plot.getAxis(name)._tickLevels[0]]


def test_spectrum_axes_label_both_ends(widget):
    """The last frequency label sits inside the axis (pyqtgraph hides one that
    would overhang it), and the bottom of the level scale reads 1e-4."""
    assert tick_labels(widget.spectrum, 'bottom')[-1] == '20kHz'
    assert tick_labels(widget.spectrum, 'left') == ['1', '0.1', '0.01', '0.001', '1e-4']


def test_curves_are_thicker_and_drawn_as_segments(widget):
    from pylzr.gui.spectrum_widget import _LINE_W, _WAVE_W
    assert widget._waveform_line.opts['pen'].widthF() == _WAVE_W > 1
    for item in widget._spectrum_lines:
        assert item.opts['pen'].widthF() == _LINE_W > _WAVE_W     # the spectrum line is the heavier one
    for item in (widget._waveform_line, *widget._spectrum_lines):
        assert item.curve.opts['segmentedLineMode'] == 'on'     # wide antialiased polylines are slow


def softened(*frames):
    """What _soften shows (as levels, not log10) after each frame in turn."""
    from pylzr.gui.spectrum_widget import _soften, _windows
    windows, held = _windows(BandLayout(2048, 44100).freqs), None
    for frame in frames:
        held = _soften(frame, windows, held)
    return 10.0 ** held


def test_gentle_smoothing_keeps_a_flat_spectrum():
    np.testing.assert_allclose(softened(spectrum(0.01)), 0.01)


def test_gentle_smoothing_spreads_a_high_spike_but_leaves_low_bins():
    frame = spectrum(1e-3)
    frame[900] = 1e-1                     # ~19.4 kHz: bins are dense on the log axis here
    frame[5] = 1e-1                       # ~108 Hz: bins are far apart, no neighbours in reach
    shown = softened(frame)
    assert 1e-3 < shown[900] < 1e-2       # lowered…
    assert shown[899] > 1e-3 < shown[901]  # …and spread to its neighbours
    assert shown[5] == pytest.approx(1e-1)
    assert shown[4] == pytest.approx(1e-3) == shown[6]


def test_gentle_smoothing_rises_at_once_and_falls_gradually():
    from pylzr.gui.spectrum_widget import _FALL_PER_FRAME
    assert softened(spectrum(1e-3), spectrum(1e-1))[10] == pytest.approx(1e-1)
    fallen = softened(spectrum(1e-1), spectrum(1e-3))[10]
    assert fallen == pytest.approx(10 ** (-1 - _FALL_PER_FRAME))
