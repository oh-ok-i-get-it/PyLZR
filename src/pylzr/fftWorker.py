
import numpy as np
from scipy.fftpack import rfft
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot

class FFTWorker(QObject):
    """
    Worker object living in its own QThread.
    Listens for raw waveform buffers and emits
    the three spectral bands when done.
    """
    resultReady = pyqtSignal(np.ndarray, np.ndarray, np.ndarray)

    def __init__(self, sp_scale, lo_cut, med_cut, hi_cut):
        super().__init__()
        self.sp_scale = sp_scale
        self.lo_cut   = lo_cut
        self.med_cut  = med_cut
        self.hi_cut   = hi_cut

    @pyqtSlot(np.ndarray)
    def process(self, wf_buffer: np.ndarray):
        # do the FFT and slicing off the GUI thread
        spec = np.abs(rfft(wf_buffer - 128)) * self.sp_scale
        low  = spec[:self.lo_cut]
        med  = spec[self.lo_cut:self.med_cut]
        hi   = spec[self.med_cut:self.hi_cut]
        # send the three bands back
        self.resultReady.emit(low, med, hi)
