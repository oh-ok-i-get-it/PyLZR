import numpy as np
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

from .bands import BandLayout


class FFTWorker(QObject):
    """Qt worker that runs a real FFT on audio chunks off the main thread.

    Emits resultReady with the scaled magnitude spectrum (chunk // 2 + 1
    bins) for each chunk; split it into bands with BandLayout.split().

    Call set_window() to change the windowing function applied before the FFT.
    Default is rectangular (no window). set_window runs on the calling thread —
    a single-frame transition artefact on switch is imperceptible.
    """

    resultReady = pyqtSignal(np.ndarray)

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
        spectrum = np.abs(np.fft.rfft(windowed)) * self._bands.scale
        self.resultReady.emit(spectrum)

    def set_window(self, name: str):
        """Switch windowing function (one of WINDOW_NAMES; unknown names fall back to rectangle)."""
        fn = self._WINDOWS.get(name, self._WINDOWS['rectangle'])
        self._window = fn(self._bands.chunk)
