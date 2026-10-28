from dataclasses import dataclass
from functools import cached_property

import numpy as np


@dataclass(frozen=True)
class BandLayout:
    """How an FFT spectrum of one audio chunk is split into low/mid/high bands.

    The single source for the band boundaries (spectrum indices), the
    spectrum scale factor and the frequency axes used to plot each band.
    """

    chunk: int    # samples per audio chunk
    rate:  int    # sample rate, Hz

    @property
    def lo_cut(self) -> int:
        return self.chunk // 128

    @property
    def med_cut(self) -> int:
        return self.chunk // 4

    @property
    def hi_cut(self) -> int:
        return self.chunk // 2 + 1

    @property
    def scale(self) -> float:
        return 2.0 / (128.0 * self.chunk)

    @cached_property
    def f_low(self) -> np.ndarray:
        return np.linspace(self.rate / self.chunk, self.rate / 128, self.lo_cut)

    @cached_property
    def f_med(self) -> np.ndarray:
        return np.linspace(self.rate / 128, self.rate / 4, self.med_cut - self.lo_cut)

    @cached_property
    def f_high(self) -> np.ndarray:
        return np.linspace(self.rate / 4, self.rate / 2, self.hi_cut - self.med_cut)

    def split(self, spectrum: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(low, mid, high) slices of a scaled spectrum."""
        return (spectrum[:self.lo_cut],
                spectrum[self.lo_cut:self.med_cut],
                spectrum[self.med_cut:self.hi_cut])
