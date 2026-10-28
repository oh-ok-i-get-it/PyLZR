import numpy as np
import pyqtgraph as pg
from PyQt5.QtWidgets import QWidget, QVBoxLayout

from ..analysis import BandLayout


class SpectrumWidget(QWidget):
    """Waveform and log-log spectrum plots.

    set_smoothing() applies an exponential moving average to the displayed
    spectrum only; the analysis always uses the raw bands.
    """

    def __init__(self, bands: BandLayout):
        super().__init__()
        self._bands = bands
        self._waveform_x = np.arange(0, 2 * bands.chunk, 2)

        self._smoothing = 0.0
        self._smoothed: list[np.ndarray] | None = None   # low, med, high

        pg.setConfigOptions(antialias=True)
        self._gfx = pg.GraphicsLayoutWidget()
        self._build_plots()

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._gfx)
        self.setLayout(layout)

    def _build_plots(self):
        chunk = self._bands.chunk
        rate  = self._bands.rate

        wf_x = pg.AxisItem(orientation='bottom')
        wf_x.setTicks([[(x, str(x)) for x in range(0, 2 * chunk + 1, chunk // 2)]])
        self.waveform = self._gfx.addPlot(title='WAVEFORM', row=1, col=1, axisItems={'bottom': wf_x})
        self.waveform.setYRange(0, 255, padding=0)
        self.waveform.setXRange(0, 2 * chunk, padding=0.005)

        sp_x = pg.AxisItem(orientation='bottom')
        sp_x.setTicks([[(np.log10(10),    '10Hz'),  (np.log10(100),   '100Hz'),
                         (np.log10(250),   '250Hz'), (np.log10(400),   '400Hz'),
                         (np.log10(1000),  '1kHz'),  (np.log10(22050), '22kHz')]])
        self.spectrum = self._gfx.addPlot(title='SPECTRUM', row=2, col=1, axisItems={'bottom': sp_x})
        self.spectrum.setLogMode(x=True, y=True)
        self.spectrum.setYRange(-4, 0, padding=0)
        self.spectrum.setXRange(np.log10(20), np.log10(rate / 2), padding=0.005)

        for plot in (self.waveform, self.spectrum):
            plot.getViewBox().keyPressEvent = lambda ev: ev.ignore()

        self._waveform_line = self.waveform.plot(pen='c')
        self._spectrum_lines = [self.spectrum.plot(pen=pen) for pen in ('y', 'b', 'm')]  # low, med, high

    def set_smoothing(self, value: float):
        """EMA factor 0.0 (off) – 0.9 (heavy)."""
        self._smoothing = value
        if value == 0.0:
            self._smoothed = None

    def update_waveform(self, chunk: np.ndarray):
        """chunk: int16 samples; drawn scaled from ±32767 to 0–255."""
        display = ((chunk.astype(np.int32) >> 8) + 128).astype(np.int16)
        self._waveform_line.setData(self._waveform_x, display)

    def update_spectrum(self, low: np.ndarray, med: np.ndarray, high: np.ndarray):
        bands = [low, med, high]
        if self._smoothing > 0.0:
            a = self._smoothing
            if self._smoothed is None:
                self._smoothed = [b.copy() for b in bands]
            else:
                self._smoothed = [a * s + (1 - a) * b for s, b in zip(self._smoothed, bands, strict=True)]
            bands = self._smoothed

        axes = (self._bands.f_low, self._bands.f_med, self._bands.f_high)
        for line, axis, data in zip(self._spectrum_lines, axes, bands, strict=True):
            line.setData(axis, data)
