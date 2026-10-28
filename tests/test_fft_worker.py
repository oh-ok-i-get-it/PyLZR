import numpy as np
import pytest

from pylzr.analysis import BandLayout, FFTWorker
from pylzr.core import CHUNK, SAMPLE_RATE

from helpers import tone_chunks

BANDS = BandLayout(CHUNK, SAMPLE_RATE)


def make_worker():
    """Single construction point — update here if the constructor changes.
    Results are stored as (low, mid, high) bands."""
    worker = FFTWorker(BANDS)
    results = []
    worker.resultReady.connect(lambda spectrum: results.append(BANDS.split(spectrum)[:3]))
    return worker, results


def test_spectrum_covers_every_bin(qapp):
    worker = FFTWorker(BANDS)
    spectra = []
    worker.resultReady.connect(spectra.append)
    worker.process(tone_chunks(1, (440, 1000))[0])
    assert len(spectra[0]) == CHUNK // 2 + 1


@pytest.mark.parametrize('freq', [100, 1000, 5000])
def test_tone_peaks_at_its_true_frequency(qapp, freq):
    """The plot and the bands use the real bin frequencies (a 1 kHz tone used
    to land near 2 kHz)."""
    worker = FFTWorker(BANDS)
    spectra = []
    worker.resultReady.connect(spectra.append)
    worker.process(tone_chunks(1, (freq, 8000))[0])
    peak_freq = BANDS.freqs[np.argmax(spectra[0])]
    assert abs(peak_freq - freq) <= SAMPLE_RATE / CHUNK / 2


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


# ── Calibration against the previous (packed-FFT) analysis ───────────────────

def legacy_band_averages(chunks):
    """LOW/HIGH window averages exactly as versions before the FFT fix computed
    them: |packed real FFT| (real and imaginary parts as separate entries,
    scipy.fftpack layout), entries [0, 16) and [512, 1025)."""
    lows, highs = [], []
    for chunk in chunks:
        c = np.fft.rfft(chunk.astype(np.float64))
        packed = np.empty(CHUNK)
        packed[0] = c[0].real
        packed[1:-1:2] = c[1:CHUNK // 2].real
        packed[2:-1:2] = c[1:CHUNK // 2].imag
        packed[-1] = c[CHUNK // 2].real
        spec = np.abs(packed) * 2.0 / (128.0 * CHUNK)
        lows.append(spec[:16].mean())
        highs.append(spec[512:1025].mean())
    return np.mean(lows) * 1000, np.mean(highs) * 10000


def band_averages(chunks):
    worker, results = make_worker()
    for chunk in chunks:
        worker.process(chunk)
    return (np.mean([low.mean() for low, _, _ in results]) * 1000,
            np.mean([high.mean() for _, _, high in results]) * 10000)


def test_averages_stay_where_they_were(qapp):
    """The 2/π calibration keeps LOW/HIGH averages — and so saved cutoffs —
    where they were before the FFT fix. Over a sweep of tones the typical
    (median) ratio is 1; single pure tones differ a little because the old
    reading depended on each tone's phase."""
    sweep = [(f, 400, 0) for f in range(40, 170, 10)] + [(f, 2000, 1) for f in range(6000, 11000, 1000)]
    ratios = []
    for freq, amp, band in sweep:
        chunks = tone_chunks(20, (freq, amp))
        ratios.append(band_averages(chunks)[band] / legacy_band_averages(chunks)[band])
    assert np.median(ratios) == pytest.approx(1.0, abs=0.02)
    assert max(abs(r - 1) for r in ratios) < 0.15
