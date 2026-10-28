import numpy as np
from scipy.fftpack import rfft
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from .bands import BandLayout


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

    def __init__(self, bands: BandLayout):
        super().__init__()
        self._bands  = bands
        self._window = self._WINDOWS['rectangle'](bands.chunk)

    @pyqtSlot(np.ndarray)
    def process(self, wf_buffer: np.ndarray):
        windowed = wf_buffer.astype(np.float32) * self._window
        spec = np.abs(rfft(windowed)) * self._bands.scale
        self.resultReady.emit(*self._bands.split(spec))

    def set_window(self, name: str):
        """Switch windowing function (one of WINDOW_NAMES; unknown names fall back to rectangle)."""
        fn = self._WINDOWS.get(name, self._WINDOWS['rectangle'])
        self._window = fn(self._bands.chunk)
