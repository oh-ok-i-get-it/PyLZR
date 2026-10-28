import numpy as np
import pytest

from pylzr.analysis import BandLayout, FFTWorker
from pylzr.core import CHUNK, SAMPLE_RATE

from helpers import tone_chunks


def make_worker():
    """Single construction point — update here if the constructor changes."""
    worker = FFTWorker(BandLayout(CHUNK, SAMPLE_RATE))
    results = []
    worker.resultReady.connect(lambda low, med, high: results.append((low, med, high)))
    return worker, results


def test_band_sizes(qapp):
    worker, results = make_worker()
    worker.process(tone_chunks(1, (440, 1000))[0])
    low, med, high = results[0]
    assert (len(low), len(med), len(high)) == (CHUNK // 128, CHUNK // 4 - CHUNK // 128, CHUNK // 4 + 1)


def test_silence_gives_zero_spectrum(qapp):
    worker, results = make_worker()
    worker.process(np.zeros(CHUNK, dtype=np.int16))
    assert all(not band.any() for band in results[0])


def test_low_tone_lands_in_low_band_and_high_tone_in_high_band(qapp):
    worker, results = make_worker()
    worker.process(tone_chunks(1, (80, 2000))[0])
    worker.process(tone_chunks(1, (8000, 2000))[0])
    (low1, _, high1), (low2, _, high2) = results
    assert low1.mean() > 10 * low2.mean()
    assert high2.mean() > 10 * high1.mean()


@pytest.mark.parametrize('name', ['hann', 'hamming', 'blackman'])
def test_window_functions_change_the_spectrum(qapp, name):
    worker, results = make_worker()
    chunk = tone_chunks(1, (80, 2000))[0]
    worker.process(chunk)
    worker.set_window(name)
    worker.process(chunk)
    worker.set_window('rectangle')
    worker.process(chunk)
    rect, windowed, rect_again = (r[0] for r in results)
    assert not np.allclose(rect, windowed)
    np.testing.assert_array_equal(rect, rect_again)


def test_unknown_window_falls_back_to_rectangle(qapp):
    worker, results = make_worker()
    chunk = tone_chunks(1, (80, 2000))[0]
    worker.process(chunk)
    worker.set_window('hann')
    worker.set_window('no-such-window')
    worker.process(chunk)
    np.testing.assert_array_equal(results[0][0], results[1][0])
