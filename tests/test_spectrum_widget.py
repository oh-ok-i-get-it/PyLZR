import numpy as np
import pytest

from pylzr.analysis import BandLayout
from pylzr.gui import SpectrumWidget


@pytest.fixture
def widget(qapp):
    return SpectrumWidget(BandLayout(2048, 44100))


def shown(widget):
    """Y data given to the low, med, high lines (before the plot's log scaling)."""
    return [line.getOriginalDataset()[1] for line in widget._spectrum_lines]


def bands(value):
    return np.full(16, value), np.full(496, value), np.full(513, value)


def test_without_smoothing_shows_raw_bands(widget):
    widget.update_spectrum(*bands(1.0))
    widget.update_spectrum(*bands(3.0))
    assert all(np.allclose(y, 3.0) for y in shown(widget))


def test_smoothing_is_an_ema_of_displayed_bands(widget):
    widget.set_smoothing(0.75)
    widget.update_spectrum(*bands(1.0))     # first frame seeds the average
    widget.update_spectrum(*bands(3.0))
    assert all(np.allclose(y, 1.5) for y in shown(widget))   # 0.75*previous + 0.25*new


def test_turning_smoothing_off_resets_it(widget):
    widget.set_smoothing(0.5)
    widget.update_spectrum(*bands(1.0))
    widget.set_smoothing(0.0)
    widget.set_smoothing(0.5)
    widget.update_spectrum(*bands(3.0))     # starts fresh, not averaged with 1.0
    assert all(np.allclose(y, 3.0) for y in shown(widget))


def test_waveform_is_scaled_to_0_255(widget):
    chunk = np.array([-32768, 0, 32767] + [0] * 2045, dtype=np.int16)
    widget.update_waveform(chunk)
    x, y = widget._waveform_line.getData()
    assert list(y[:3]) == [0, 128, 255] and len(x) == 2048
