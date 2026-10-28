import numpy as np

from pylzr.analysis import BandLayout


def test_default_layout():
    bands = BandLayout(chunk=2048, rate=44100)
    assert (bands.lo_cut, bands.med_cut, bands.hi_cut) == (16, 512, 1025)
    assert bands.scale == 2.0 / (128.0 * 2048)
    assert len(bands.f_low) == 16 and len(bands.f_med) == 496 and len(bands.f_high) == 513
    assert bands.f_low[0] == 44100 / 2048 and bands.f_high[-1] == 44100 / 2


def test_split_matches_axes():
    bands = BandLayout(chunk=1024, rate=48000)
    low, med, high = bands.split(np.arange(1024, dtype=float))
    assert (len(low), len(med), len(high)) == (len(bands.f_low), len(bands.f_med), len(bands.f_high))
    assert low[0] == 0 and med[0] == bands.lo_cut and high[0] == bands.med_cut
