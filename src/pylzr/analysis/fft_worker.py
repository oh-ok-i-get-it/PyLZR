import numpy as np
from scipy.fftpack import rfft
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot


class FFTWorker(QObject):
    """Qt worker that runs rfft on audio chunks off the main thread.

    Emits resultReady with three frequency-band arrays (low, mid, high)
    each time a chunk is processed.

    Call set_window() to change the windowing function applied before the FFT.
    Default is rectangular (no window). set_window runs on the calling thread —
    a single-frame transition artefact on switch is imperceptible.
    """

    resultReady = pyqtSignal(np.ndarray, np.ndarray, np.ndarray)

    _WINDOWS = {
        'rectangle': lambda n: np.ones(n, dtype=np.float32),
        'hann':      lambda n: np.hanning(n).astype(np.float32),
        'hamming':   lambda n: np.hamming(n).astype(np.float32),
        'blackman':  lambda n: np.blackman(n).astype(np.float32),
    }
    WINDOW_NAMES = tuple(_WINDOWS)   # valid set_window() names, rectangle first

    def __init__(self, sp_scale: float, lo_cut: int, med_cut: int,
                 hi_cut: int, chunk: int):
        super().__init__()
        self.sp_scale = sp_scale
        self.lo_cut   = lo_cut
        self.med_cut  = med_cut
        self.hi_cut   = hi_cut
        self._chunk   = chunk
        self._window  = np.ones(chunk, dtype=np.float32)  # rectangle

    @pyqtSlot(np.ndarray)
    def process(self, wf_buffer: np.ndarray):
        windowed = wf_buffer.astype(np.float32) * self._window
        spec = np.abs(rfft(windowed)) * self.sp_scale
        low  = spec[:self.lo_cut]
        med  = spec[self.lo_cut:self.med_cut]
        hi   = spec[self.med_cut:self.hi_cut]
        self.resultReady.emit(low, med, hi)

    def set_window(self, name: str):
        """Switch windowing function (one of WINDOW_NAMES; unknown names fall back to rectangle)."""
        fn = self._WINDOWS.get(name, self._WINDOWS['rectangle'])
        self._window = fn(self._chunk)
