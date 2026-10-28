import math

import numpy as np
import pytest

from pylzr.analysis import BandLayout


def test_default_layout_frequency_ranges():
    bands = BandLayout(chunk=2048, rate=44100)
    assert (bands.lo_cut, bands.med_cut, bands.hi_cut) == (8, 256, 513)
    low, mid, high, top = bands.split(bands.freqs)
    assert low[0] == 0 and mid[0] == pytest.approx(172.27, abs=0.01)   # low: 0 – 172 Hz
    assert high[0] == 5512.5 and high[-1] == 11025                       # high: 5.5 – 11 kHz
    assert top[0] > 11025 and top[-1] == 22050                           # top: up to Nyquist
    assert bands.scale == pytest.approx(2.0 / (128.0 * 2048) * 2 / math.pi)


def test_split_covers_every_bin_once():
    bands = BandLayout(chunk=1024, rate=48000)
    parts = bands.split(np.arange(1024 // 2 + 1))
    np.testing.assert_array_equal(np.concatenate(parts), np.arange(513))
