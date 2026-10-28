import math
from dataclasses import dataclass
from functools import cached_property

import numpy as np


@dataclass(frozen=True)
class BandLayout:
    """How the FFT spectrum of one audio chunk is split into bands.

    The single source for the band boundaries (bin indices into the
    chunk // 2 + 1 bins of a real FFT), the spectrum scale factor and the
    frequency of every bin. With the defaults (2048 samples at 44.1 kHz,
    21.5 Hz per bin):

        low   bins [0, 8)      0 – 172 Hz     analysed (LOW average)
        mid   bins [8, 256)    172 Hz – 5.5 kHz
        high  bins [256, 513)  5.5 – 11 kHz   analysed (HIGH average)
        top   bins [513, ...)  11 – 22 kHz    display only
    """

    chunk: int    # samples per audio chunk
    rate:  int    # sample rate, Hz

    @property
    def lo_cut(self) -> int:
        return self.chunk // 256

    @property
    def med_cut(self) -> int:
        return self.chunk // 8

    @property
    def hi_cut(self) -> int:
        return self.chunk // 4 + 1

    @property
    def scale(self) -> float:
        # Earlier versions averaged |real| and |imag| of a packed FFT
        # separately, which reads (|cos φ| + |sin φ|) / 2 of the true magnitude:
        # 2/π on average over phase. Scaling true magnitudes by 2/π keeps band
        # averages — and so every saved cutoff — where they were.
        return 2.0 / (128.0 * self.chunk) * (2.0 / math.pi)

    @cached_property
    def freqs(self) -> np.ndarray:
        """Centre frequency (Hz) of every FFT bin."""
        return np.fft.rfftfreq(self.chunk, 1.0 / self.rate)

    def split(self, spectrum: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """(low, mid, high, top) slices of a spectrum or of `freqs`."""
        return (spectrum[:self.lo_cut],
                spectrum[self.lo_cut:self.med_cut],
                spectrum[self.med_cut:self.hi_cut],
                spectrum[self.hi_cut:])
