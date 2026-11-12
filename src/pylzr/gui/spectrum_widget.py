import numpy as np
import pyqtgraph as pg
from PyQt5.QtCore import QPointF, Qt
from PyQt5.QtGui import QBrush, QColor, QFont, QLinearGradient
from PyQt5.QtWidgets import QWidget, QVBoxLayout

from . import style, theme
from ..analysis import BandLayout

# Spectrum lines: low, mid, high, top (not analysed). Curves wider than 1 px are
# drawn as separate segments: as one antialiased polyline they take ~30 ms a
# frame instead of ~4 ms.
_BAND_COLOURS = (theme.LOW_BAND, theme.MID_BAND, theme.HIGH_BAND, theme.TOP_BAND)
_LINE_W       = 1.5                                  # spectrum curve, px
_WAVE_W       = 1.2                                  # waveform curve, px: thinner keeps its dense detail crisp
_FILLED       = (theme.LOW_BAND, theme.HIGH_BAND)   # the analysed bands get a fill that fades downwards
_FILL_TOP_ALPHA = 0.22                               # at the top of the plot; 0 turns the fill off
_SPEC_Y       = (-4, 0)                              # spectrum view, log10 units: 1e-4 … 1

# Gentle display smoothing (see _soften), in log10 units like the plot
_SMOOTH_OCTAVE = 1 / 32    # each bin averaged with its neighbours within ± this many octaves
_FALL_PER_FRAME = 0.04     # how far a level may drop per frame, in decades (rises are instant)
_FLOOR          = 1e-12    # levels below this count as this (log10 of 0 is -inf)
_TITLE_TRACKING = 1.5    # px between title letters, like the small-caps titles elsewhere
_ROW_STRETCH  = (1, 2)   # waveform : spectrum height


def _fade(colour: str) -> QBrush:
    """Fill brush: `colour` at _FILL_TOP_ALPHA at the top of the spectrum view,
    fading to clear at the bottom. Set in data units (log10), which is what
    the curve paints in."""
    top, clear = QColor(colour), QColor(colour)
    top.setAlphaF(_FILL_TOP_ALPHA)
    clear.setAlphaF(0.0)
    gradient = QLinearGradient(QPointF(0, _SPEC_Y[1]), QPointF(0, _SPEC_Y[0]))
    gradient.setColorAt(0.0, top)
    gradient.setColorAt(1.0, clear)
    return QBrush(gradient)


def _windows(freqs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """For every bin, the first and one-past-last bin within ±_SMOOTH_OCTAVE of
    its frequency. Low bins are far apart on a log axis and get only
    themselves; dense high bins get a few neighbours on each side."""
    ratio = 2.0 ** _SMOOTH_OCTAVE
    return (np.searchsorted(freqs, freqs / ratio, side='left'),
            np.searchsorted(freqs, freqs * ratio, side='right'))


def _soften(spectrum: np.ndarray, windows: tuple[np.ndarray, np.ndarray],
            previous: np.ndarray | None) -> np.ndarray:
    """The spectrum as drawn, in log10 units: each bin averaged over its window
    (log units, so deep dips don't dominate), then held so it falls at most
    _FALL_PER_FRAME below `previous` (the last result); rises show at once."""
    levels = np.log10(np.maximum(spectrum, _FLOOR))
    lo, hi = windows
    sums = np.concatenate(([0.0], np.cumsum(levels)))
    levels = (sums[hi] - sums[lo]) / (hi - lo)
    if previous is not None:
        levels = np.maximum(levels, previous - _FALL_PER_FRAME)
    return levels


class SpectrumWidget(QWidget):
    """Waveform and log-log spectrum plots.

    The spectrum is drawn against each FFT bin's true frequency, coloured by
    band (low gold, mid grey, high purple, as elsewhere in the app); the
    11–22 kHz range, which is not analysed, is dim grey.

    What is drawn is smoothed for the eye only; the analysis always uses raw
    data. With `gentle` (the default) neighbouring frequencies are averaged a
    little and levels fall back gradually (see _soften); set_smoothing() adds
    an exponential moving average on top.
    """

    def __init__(self, bands: BandLayout, gentle: bool = True):
        super().__init__()
        self._bands = bands
        self._waveform_x = np.arange(0, 2 * bands.chunk, 2)

        self._windows = _windows(bands.freqs) if gentle else None
        self._held: np.ndarray | None = None       # last _soften result (log10)

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
        wf_y = pg.AxisItem(orientation='left')
        wf_y.setTicks([[(v, str(v)) for v in (0, 128, 255)]])          # bottom, centre line, top
        self.waveform = self._gfx.addPlot(title='WAVEFORM', row=1, col=1, axisItems={'bottom': wf_x, 'left': wf_y})
        self.waveform.setYRange(0, 255, padding=0)
        self.waveform.setXRange(0, 2 * chunk, padding=0.005)

        sp_x = pg.AxisItem(orientation='bottom')
        # 20 kHz, not 22: pyqtgraph hides a label that would overhang the end of the axis
        sp_x.setTicks([[(np.log10(10),    '10Hz'),  (np.log10(100),   '100Hz'),
                         (np.log10(250),   '250Hz'), (np.log10(400),   '400Hz'),
                         (np.log10(1000),  '1kHz'),  (np.log10(20000), '20kHz')]])
        sp_y = pg.AxisItem(orientation='left')
        sp_y.setTicks([[(0, '1'), (-1, '0.1'), (-2, '0.01'), (-3, '0.001'), (-4, '1e-4')]])
        self.spectrum = self._gfx.addPlot(title='SPECTRUM', row=2, col=1, axisItems={'bottom': sp_x, 'left': sp_y})
        self.spectrum.setLogMode(x=True, y=True)
        self.spectrum.setYRange(*_SPEC_Y, padding=0)
        self.spectrum.setXRange(np.log10(20), np.log10(rate / 2), padding=0.005)

        # Grid steps: waveform every half chunk and quarter of its range; spectrum
        # every decade (its view is in log10 units)
        for plot, title, grid_x, grid_y in ((self.waveform, 'WAVEFORM', chunk // 2, 64),
                                            (self.spectrum, 'SPECTRUM', 1, 1)):
            plot.getViewBox().keyPressEvent = lambda ev: ev.ignore()
            self._style_plot(plot, title, grid_x, grid_y)

        grid = self._gfx.ci.layout
        for row, stretch in zip((1, 2), _ROW_STRETCH, strict=True):
            grid.setRowStretchFactor(row, stretch)

        self._waveform_line = self._curve(self.waveform, theme.ACCENT, width=_WAVE_W)
        # low, mid, high, top (not analysed); the fill reaches down to the bottom of the view
        self._spectrum_lines = []
        for colour in _BAND_COLOURS:
            fill = _fade(colour) if colour in _FILLED and _FILL_TOP_ALPHA > 0 else None
            self._spectrum_lines.append(self._curve(self.spectrum, colour, fill))
        self._spectrum_x = self._drawn(self._bands.split(self._bands.freqs))

    @staticmethod
    def _curve(plot, colour: str, fill: QBrush | None = None, width: float = _LINE_W) -> pg.PlotDataItem:
        """A curve `width` px wide, drawn as segments (see _LINE_W). Flat caps: round ones
        look the same at this width but cost ~2.5 ms more a frame."""
        pen = pg.mkPen(colour, width=width)
        pen.setCapStyle(Qt.FlatCap)
        item = plot.plot(pen=pen, fillLevel=_SPEC_Y[0] if fill else None, brush=fill)
        item.curve.setSegmentedLineMode('on')
        return item

    @staticmethod
    def _style_plot(plot, title: str, grid_x: float, grid_y: float):
        """Dim letter-spaced title, axis text in the UI font, a fixed-width left
        axis (so both plots line up) and a faint grid. The grid is a separate
        item: the axes' own grid hides the edge tick labels (0, 1)."""
        plot.setTitle(f'<span style="letter-spacing:{_TITLE_TRACKING}px">{title}</span>',
                      color=theme.TEXT_DIM, size='8pt', bold=True)
        font = QFont(theme.UI_FONT)
        font.setPixelSize(theme.SIZE_LABEL)
        font.setWeight(style.text_weight())
        for name in ('left', 'bottom'):
            axis = plot.getAxis(name)
            axis.setPen(pg.mkPen(theme.AXIS_LINE))
            axis.setTextPen(pg.mkPen(theme.AXIS))
            axis.setStyle(tickFont=font)
        plot.getAxis('left').setWidth(theme.PLOT_AXIS_W)
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
        """The band pieces as drawn: bin 0 (DC) dropped, since the log x-axis
        can't show 0 Hz, and every band after the first starting at the
        previous band's last bin, so the line has no gaps between colours."""
        low, *rest = segments
        drawn = [low[1:]]
        for segment in rest:
            drawn.append(np.concatenate((drawn[-1][-1:], segment)))
        return drawn

    def update_spectrum(self, spectrum: np.ndarray):
        if self._windows is not None:
            self._held = _soften(spectrum, self._windows, self._held)
            spectrum = 10.0 ** self._held
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
