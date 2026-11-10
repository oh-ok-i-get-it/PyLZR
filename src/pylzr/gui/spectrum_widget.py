import numpy as np
import pyqtgraph as pg
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import QWidget, QVBoxLayout

from . import theme
from ..analysis import BandLayout

# Spectrum lines: low, mid, high, top (not analysed). Lines stay 1 px wide:
# wider antialiased lines are far slower to draw.
_BAND_COLOURS = (theme.LOW_BAND, theme.MID_BAND, theme.HIGH_BAND, theme.TOP_BAND)
_FILLED       = (theme.LOW_BAND, theme.HIGH_BAND)   # the analysed bands get a soft fill
_FILL_ALPHA   = 0.10                                 # 0 turns the fill off


class SpectrumWidget(QWidget):
    """Waveform and log-log spectrum plots.

    The spectrum is drawn against each FFT bin's true frequency, coloured by
    band (low gold, mid grey, high purple, as elsewhere in the app); the
    11–22 kHz range, which is not analysed, is dim grey. set_smoothing()
    applies an exponential moving average to the displayed spectrum only;
    the analysis always uses raw data.
    """

    def __init__(self, bands: BandLayout):
        super().__init__()
        self._bands = bands
        self._waveform_x = np.arange(0, 2 * bands.chunk, 2)

        self._smoothing = 0.0
        self._smoothed: np.ndarray | None = None

        pg.setConfigOptions(antialias=True)
        self._gfx = pg.GraphicsLayoutWidget()
        self._gfx.setBackground(theme.BG)
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

        # Grid steps: waveform every half chunk and 50 levels; spectrum every decade
        # (its view is in log10 units)
        for plot, title, grid_x, grid_y in ((self.waveform, 'WAVEFORM', chunk // 2, 50),
                                            (self.spectrum, 'SPECTRUM', 1, 1)):
            plot.getViewBox().keyPressEvent = lambda ev: ev.ignore()
            self._style_plot(plot, title, grid_x, grid_y)

        self._waveform_line = self.waveform.plot(pen=pg.mkPen(theme.ACCENT, width=1))
        # low, mid, high, top (not analysed); the spectrum's y range starts at log10 = -4
        self._spectrum_lines = []
        for colour in _BAND_COLOURS:
            fill = None
            if colour in _FILLED and _FILL_ALPHA > 0:
                fill = QColor(colour)
                fill.setAlphaF(_FILL_ALPHA)
            self._spectrum_lines.append(self.spectrum.plot(
                pen=pg.mkPen(colour, width=1), fillLevel=-4 if fill else None, brush=fill))
        # The log x-axis can't show 0 Hz, so bin 0 (DC) is not drawn
        self._spectrum_x = self._drawn(self._bands.split(self._bands.freqs))

    @staticmethod
    def _style_plot(plot, title: str, grid_x: float, grid_y: float):
        """Dim title, axis text in the UI font, and a faint grid. The grid is a
        separate item: the axes' own grid hides the edge tick labels (0, 1)."""
        plot.setTitle(title, color=theme.TEXT_DIM, size='8pt', bold=True)
        font = QFont(theme.UI_FONT)
        font.setPixelSize(theme.SIZE_LABEL)
        for name in ('left', 'bottom'):
            axis = plot.getAxis(name)
            axis.setPen(pg.mkPen(theme.AXIS_LINE))
            axis.setTextPen(pg.mkPen(theme.AXIS))
            axis.setStyle(tickFont=font)
        grid = pg.GridItem(pen=pg.mkPen(theme.GRID), textPen=None)
        grid.setTickSpacing(x=[grid_x], y=[grid_y])
        grid.setZValue(-100)                 # behind the lines
        plot.addItem(grid, ignoreBounds=True)

    def set_smoothing(self, value: float):
        """EMA factor 0.0 (off) – 0.9 (heavy)."""
        self._smoothing = value
        if value == 0.0:
            self._smoothed = None

    def update_waveform(self, chunk: np.ndarray):
        """chunk: int16 samples; drawn scaled from ±32767 to 0–255."""
        display = ((chunk.astype(np.int32) >> 8) + 128).astype(np.int16)
        self._waveform_line.setData(self._waveform_x, display)

    @staticmethod
    def _drawn(segments):
        low, *rest = segments
        return [low[1:], *rest]

    def update_spectrum(self, spectrum: np.ndarray):
        if self._smoothing > 0.0:
            a = self._smoothing
            if self._smoothed is None:
                self._smoothed = spectrum.copy()
            else:
                self._smoothed = a * self._smoothed + (1 - a) * spectrum
            spectrum = self._smoothed

        segments = self._drawn(self._bands.split(spectrum))
        for line, x, y in zip(self._spectrum_lines, self._spectrum_x, segments, strict=True):
            line.setData(x, y)
