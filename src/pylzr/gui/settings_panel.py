from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QFrame, QSlider, QPushButton, QProgressBar,
)
from PyQt5.QtCore import Qt, QSize, pyqtSignal
from ..analysis import FFTWorker
from ..core import CONTROL_MODES
from . import style, theme
from .dmx_settings import DMXSettings
from .panel_style import ICON_BUTTON_STYLE, SMALL_BUTTON_STYLE, label, pad, section

_W = 560  # panel width — wide enough for 3 columns

# Dropdowns and sliders use the app-wide look (gui/style.py)
_PANEL_STYLE = (
    'QWidget#SettingsPanel {'
    f'  background: {theme.CARD};'
    f'  border: 1px solid {theme.BORDER_STRONG};'
    f'  border-top: 2px solid {theme.ACCENT};'
    f'  border-radius: {theme.RADIUS_CARD}px;'
    '}'
)

_VALUE_STYLE   = f'color: {theme.TEXT}; font-size: {theme.SIZE_LABEL}px; background: transparent;'
_READOUT_STYLE = (
    f'color: {theme.TEXT_DIM}; font-family: "{theme.MONO_FONT}"; font-size: {theme.SIZE_LABEL}px;'
    ' background: transparent;'
)
_DIAG_STYLE    = (
    f'color: {theme.TEXT}; font-family: "{theme.MONO_FONT}"; font-size: {theme.SIZE_LABEL}px;'
    ' font-weight: bold; background: transparent;'
)

_LEVEL_STYLE = (
    'QProgressBar {'
    f'  background: {theme.RAISED}; border: 1px solid {theme.BORDER_STRONG};'
    '  border-radius: 4px; text-align: center;'
    '}'
    'QProgressBar::chunk {'
    '  background: qlineargradient(x1:0,y1:0,x2:1,y2:0,'
    f'    stop:0 {theme.OK}, stop:0.6 #f39c12, stop:1 {theme.ERROR});'
    '  border-radius: 2px;'
    '}'
)

_IND_ON      = f'border-radius:5px; background:{theme.OK};'
_IND_SENT    = f'border-radius:5px; background:{theme.ACCENT};'
_IND_WARN    = f'border-radius:5px; background:{theme.WARN};'
_IND_OFF     = f'border-radius:5px; background:{theme.ERROR};'
_IND_NA      = 'border-radius:5px; background:#383838;'

# DMXOutput status state -> indicator: green once the node answers, blue
# while sending without an answer (some nodes never answer; not an error)
_DMX_DOTS = {'off': _IND_NA, 'connected': _IND_ON, 'sending': _IND_SENT, 'warning': _IND_WARN,
             'error': _IND_OFF}
_CLIP_BASE   = f'border-radius:3px; font-family:"{theme.MONO_FONT}"; font-size:8px; font-weight:bold; padding:1px 3px;'
_CLIP_ON     = _CLIP_BASE + f' background:{theme.ERROR}; color:#fff;'
_CLIP_OFF    = _CLIP_BASE + f' background:{theme.RAISED}; color:{theme.DISABLED};'
_DIV_STYLE   = f'background:{theme.DIVIDER}; border:none;'

# (label, value) choices for the fixed dropdowns
_LOG_LEVELS    = [('Info', 'info'), ('Debug', 'debug'), ('Quiet', 'quiet')]
_MODE_LABELS   = {'DMX': 'DMX (Art-Net)'}
_CONTROL_MODES = [(_MODE_LABELS.get(mode, mode), mode) for mode in CONTROL_MODES]

# ── Small helpers ─────────────────────────────────────────────────────────────

def _dot() -> QLabel:
    d = QLabel()
    d.setFixedSize(10, 10)
    d.setStyleSheet(_IND_NA)
    return d


def _divider(shape: QFrame.Shape) -> QFrame:
    """1px line: QFrame.HLine (horizontal) or QFrame.VLine (vertical)."""
    f = QFrame()
    f.setFrameShape(shape)
    if shape == QFrame.HLine:
        f.setFixedHeight(1)
    else:
        f.setFixedWidth(1)
    f.setStyleSheet(_DIV_STYLE)
    return f


# ── Column builder helpers ────────────────────────────────────────────────────

def _labeled_control(label_text: str, readout: QLabel | None,
                     control: QWidget, spacing: int = 4) -> QVBoxLayout:
    """Label row (text left, optional readout right) + control below."""
    v = QVBoxLayout()
    v.setSpacing(spacing)
    v.setContentsMargins(0, 0, 0, 0)

    hdr = QHBoxLayout()
    hdr.setContentsMargins(0, 0, 0, 0)
    hdr.addWidget(label(label_text))
    if readout is not None:
        hdr.addStretch(1)
        hdr.addWidget(readout)

    v.addLayout(hdr)
    v.addWidget(control)
    return v


def _fill_combo(combo: QComboBox, items: list[tuple[str, object]],
                current: object = None, fallback_row: int = -1):
    """Replace combo items without emitting signals.

    items are (label, value) pairs; each value is stored on its item and read
    back with combo.itemData(). Long labels are truncated for display. Selects
    the item whose value == current, else fallback_row (-1 = none).
    """
    combo.blockSignals(True)
    combo.clear()
    for text, value in items:
        combo.addItem(text if len(text) <= 32 else text[:30] + '…', value)
    row = combo.findData(current) if current is not None else -1
    combo.setCurrentIndex(row if row >= 0 else fallback_row)
    combo.blockSignals(False)


def _select_data(combo: QComboBox, value: object):
    """Select the item whose value is `value` (emits if the selection changes)."""
    row = combo.findData(value)
    if row >= 0:
        combo.setCurrentIndex(row)


# ── Main class ────────────────────────────────────────────────────────────────

class SettingsPanel(QWidget):
    """Floating settings panel anchored below the gear button.

    Positioned as a child widget of the main window with no layout slot.
    Shown/hidden and repositioned by _toggle_settings in main_window.

    Signals:
        audio_device_changed(int)  — PyAudio device index
        audio_gain_changed(float)  — 0.25 – 4.0
        midi_port_changed(str)     — port label from MIDIOutput.list_ports()
        fft_window_changed(str)    — 'rectangle' | 'hann' | 'hamming' | 'blackman'
        smoothing_changed(float)   — 0.0 – 0.9
        log_level_changed(str)     — 'debug' | 'info' | 'quiet'
        app_sm_toggled()
        control_mode_changed(str)  — one of core.CONTROL_MODES ('MIDI' | 'DMX')
        reset_requested()          — 'Reset to defaults' clicked
        audio_devices_refresh_requested() — ↻ next to the input device clicked

    The set_*() setters change a control as if the user had, emitting its
    signal when the value changes (used to restore saved settings).

    The DMX (ART-NET) section is its own widget, `dmx` (a DMXSettings, with
    its own signals and setters); the DMX indicator under CONNECTIONS stays
    here (set_dmx_status).
    """

    audio_device_changed = pyqtSignal(int)
    audio_gain_changed   = pyqtSignal(float)
    midi_port_changed    = pyqtSignal(str)
    fft_window_changed   = pyqtSignal(str)
    smoothing_changed    = pyqtSignal(float)
    log_level_changed    = pyqtSignal(str)
    app_sm_toggled       = pyqtSignal()
    control_mode_changed = pyqtSignal(str)
    reset_requested      = pyqtSignal()
    audio_devices_refresh_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('SettingsPanel')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(_PANEL_STYLE)
        self.setFixedWidth(_W)
        self._build()
        self.adjustSize()

    # ── Layout ────────────────────────────────────────────────────────────

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_top())
        root.addWidget(_divider(QFrame.HLine))
        root.addWidget(self._build_columns())
        root.addWidget(_divider(QFrame.HLine))
        self.dmx = DMXSettings()             # DMX (ART-NET): node address, tester
        root.addWidget(self.dmx)
        root.addWidget(_divider(QFrame.HLine))
        root.addWidget(self._build_performance())

    def _build_top(self) -> QWidget:
        """Connections (horizontal indicators) + Signal Level bar."""
        v = QVBoxLayout()
        v.setSpacing(8)

        # ── CONNECTIONS row ───────────────────────────────────────────────
        v.addWidget(section('CONNECTIONS'))

        conn = QHBoxLayout()
        conn.setContentsMargins(0, 0, 0, 0)
        conn.setSpacing(0)

        for i, (dot_attr, val_attr, text) in enumerate((
            ('_audio_dot', '_audio_val', 'Audio In'),
            ('_midi_dot',  '_midi_val',  'MIDI'),
            ('_dmx_dot',   '_dmx_val',   'DMX'),
        )):
            dot = _dot()
            setattr(self, dot_attr, dot)
            val = QLabel('—')
            val.setStyleSheet(_VALUE_STYLE)
            setattr(self, val_attr, val)

            grp = QHBoxLayout()
            grp.setSpacing(5)
            grp.setContentsMargins(0, 0, 0, 0)
            grp.addWidget(dot)
            grp.addWidget(label(text))
            grp.addWidget(val)

            conn.addLayout(grp)
            if i < 2:
                conn.addStretch(1)

        v.addLayout(conn)

        # ── SIGNAL LEVEL ──────────────────────────────────────────────────
        v.addWidget(section('SIGNAL LEVEL'))

        bar_row = QHBoxLayout()
        bar_row.setSpacing(6)
        bar_row.setContentsMargins(0, 0, 0, 0)

        self._level_bar = QProgressBar()
        self._level_bar.setRange(0, 100)
        self._level_bar.setValue(0)
        self._level_bar.setTextVisible(False)
        self._level_bar.setFixedHeight(8)
        self._level_bar.setStyleSheet(_LEVEL_STYLE)

        self._clip_lbl = QLabel('CLIP')
        self._clip_lbl.setFixedSize(28, 14)
        self._clip_lbl.setAlignment(Qt.AlignCenter)
        self._clip_lbl.setStyleSheet(_CLIP_OFF)

        bar_row.addWidget(self._level_bar)
        bar_row.addWidget(self._clip_lbl)
        v.addLayout(bar_row)

        return pad(v, t=10, b=10)

    def _build_columns(self) -> QWidget:
        """Three side-by-side setting columns: Audio | Analysis | App."""
        h = QHBoxLayout()
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        h.addWidget(self._build_audio_col(),    stretch=1)
        h.addWidget(_divider(QFrame.VLine))
        h.addWidget(self._build_analysis_col(), stretch=1)
        h.addWidget(_divider(QFrame.VLine))
        h.addWidget(self._build_app_col(),      stretch=1)

        w = QWidget()
        w.setStyleSheet('background:transparent;')
        w.setLayout(h)
        return w

    def _build_audio_col(self) -> QWidget:
        v = QVBoxLayout()
        v.setSpacing(10)

        v.addWidget(section('AUDIO'))

        # Device dropdown (filled by set_audio_devices) + rescan button
        self._device_combo = self._dropdown(self.audio_device_changed, placeholder='No devices found')
        self._rescan_btn = QPushButton('↻')
        self._rescan_btn.setFixedSize(24, 22)
        self._rescan_btn.setStyleSheet(ICON_BUTTON_STYLE)
        rescan_icon = style.icon('rotate-cw', theme.TEXT_DIM, size=13)
        if not rescan_icon.isNull():            # otherwise the ↻ glyph stays
            self._rescan_btn.setIcon(rescan_icon)
            self._rescan_btn.setIconSize(QSize(13, 13))
            self._rescan_btn.setText('')
        self._rescan_btn.setToolTip('Rescan audio inputs (briefly pauses audio)')
        self._rescan_btn.clicked.connect(lambda: self.audio_devices_refresh_requested.emit())
        device_row = QHBoxLayout()
        device_row.setContentsMargins(0, 0, 0, 0)
        device_row.setSpacing(4)
        device_row.addWidget(self._device_combo, stretch=1)
        device_row.addWidget(self._rescan_btn)
        device_widget = QWidget()
        device_widget.setStyleSheet('background:transparent;')
        device_widget.setLayout(device_row)
        v.addLayout(_labeled_control('Device', None, device_widget))

        # Gain slider
        self._gain_readout = QLabel('100%')
        self._gain_readout.setStyleSheet(_READOUT_STYLE)
        self._gain_slider = QSlider(Qt.Horizontal)
        self._gain_slider.setRange(25, 400)
        self._gain_slider.setValue(100)
        self._gain_slider.valueChanged.connect(self._on_gain_changed)
        v.addLayout(_labeled_control('Input Gain', self._gain_readout, self._gain_slider))

        v.addStretch(1)
        return pad(v, l=14, r=10)

    def _build_analysis_col(self) -> QWidget:
        v = QVBoxLayout()
        v.setSpacing(10)

        v.addWidget(section('ANALYSIS'))

        # Window function dropdown
        self._window_combo = self._dropdown(
            self.fft_window_changed, [(name.capitalize(), name) for name in FFTWorker.WINDOW_NAMES])
        v.addLayout(_labeled_control('FFT Window', None, self._window_combo))

        # Smoothing slider
        self._smooth_readout = QLabel('0.0')
        self._smooth_readout.setStyleSheet(_READOUT_STYLE)
        self._smooth_slider = QSlider(Qt.Horizontal)
        self._smooth_slider.setRange(0, 90)
        self._smooth_slider.setValue(0)
        self._smooth_slider.valueChanged.connect(self._on_smooth_changed)
        v.addLayout(_labeled_control('Smoothing', self._smooth_readout, self._smooth_slider))

        v.addStretch(1)
        return pad(v, l=10, r=10)

    def _build_app_col(self) -> QWidget:
        v = QVBoxLayout()
        v.setSpacing(10)

        v.addWidget(section('APP'))

        # MIDI output port dropdown (filled by set_midi_ports)
        self._midi_combo = self._dropdown(self.midi_port_changed, placeholder='No MIDI ports')
        v.addLayout(_labeled_control('MIDI Out', None, self._midi_combo))

        # Control Mode dropdown
        self._mode_combo = self._dropdown(self.control_mode_changed, _CONTROL_MODES)
        self._mode_combo.setToolTip('Where cues go: MIDI (e.g. to SoundSwitch), or DMX straight to an '
                                    'Art-Net node (set up below).')
        v.addLayout(_labeled_control('Control Mode', None, self._mode_combo))

        # Log Level dropdown
        self._log_combo = self._dropdown(self.log_level_changed, _LOG_LEVELS)
        v.addLayout(_labeled_control('Log Level', None, self._log_combo))

        # Sound Mode toggle
        sm_row = QHBoxLayout()
        sm_row.setContentsMargins(0, 0, 0, 0)
        sm_row.setSpacing(8)
        sm_row.addWidget(label('Sound Mode'))
        self._sm_btn = QPushButton('OFF')
        self._sm_btn.setCheckable(True)
        self._sm_btn.setFixedHeight(22)
        self._sm_btn.setStyleSheet(SMALL_BUTTON_STYLE)
        self._sm_btn.clicked.connect(lambda: self.app_sm_toggled.emit())
        sm_row.addWidget(self._sm_btn)
        sm_row.addStretch(1)
        v.addLayout(sm_row)

        # Reset saved settings
        self._reset_btn = QPushButton('Reset to defaults')
        self._reset_btn.setFixedHeight(22)
        self._reset_btn.setStyleSheet(SMALL_BUTTON_STYLE)
        self._reset_btn.setToolTip('Restore every setting (cutoffs, rate, gain, devices, …) to its default.')
        self._reset_btn.clicked.connect(lambda: self.reset_requested.emit())
        v.addWidget(self._reset_btn)

        v.addStretch(1)
        return pad(v, l=10, r=14)

    def _build_performance(self) -> QWidget:
        """Full-width diagnostics bar at the bottom."""
        h = QHBoxLayout()
        h.setSpacing(24)

        h.addWidget(section('PERFORMANCE'))
        h.addWidget(_divider(QFrame.VLine))

        for attr, text in (('_diag_fps', 'FFT Rate'), ('_diag_overflow', 'Overflow')):
            col = QHBoxLayout()
            col.setSpacing(6)
            col.addWidget(label(text))
            val = QLabel('—')
            val.setStyleSheet(_DIAG_STYLE)
            col.addWidget(val)
            setattr(self, attr, val)
            h.addLayout(col)

        h.addStretch(1)
        return pad(h, t=7, b=9)

    @staticmethod
    def _dropdown(signal, items: list[tuple[str, object]] = (), placeholder: str = '') -> QComboBox:
        """Styled combo of (label, value) items that emits signal(value) when
        the user picks an item."""
        combo = QComboBox()
        combo.setPlaceholderText(placeholder)
        _fill_combo(combo, list(items), fallback_row=0)

        def forward(row: int):
            if row >= 0:
                signal.emit(combo.itemData(row))
        combo.currentIndexChanged.connect(forward)
        return combo

    # ── Public setters ────────────────────────────────────────────────────

    def set_audio_status(self, connected: bool, detail: str = ''):
        self._audio_dot.setStyleSheet(_IND_ON if connected else _IND_OFF)
        text = detail or ('OK' if connected else 'Error')
        self._audio_val.setText(text[:24] + ('…' if len(text) > 24 else ''))

    def set_midi_status(self, connected: bool, port_name: str = ''):
        self._midi_dot.setStyleSheet(_IND_ON if connected else _IND_OFF)
        text = port_name or ('OK' if connected else 'Error')
        self._midi_val.setText(text[:22] + ('…' if len(text) > 22 else ''))

    def set_dmx_status(self, state: str = 'off', detail: str = 'Off'):
        """state: a DMXOutput status — 'off' | 'connected' | 'sending' | 'warning' | 'error'.
        Long details are shortened; the full text is in the tooltip."""
        self._dmx_dot.setStyleSheet(_DMX_DOTS[state])
        self._dmx_val.setText(detail[:22] + ('…' if len(detail) > 22 else ''))
        self._dmx_val.setToolTip(detail)

    def set_control_mode(self, mode: str):
        _select_data(self._mode_combo, mode)

    def set_audio_devices(self, devices: list[tuple[int, str]], current_index: int):
        """devices are (PyAudio index, name); an unknown current selects the first."""
        _fill_combo(self._device_combo, [(name, idx) for idx, name in devices],
                    current_index, fallback_row=0)

    def set_midi_ports(self, ports: list[str], current: str | None):
        """current=None leaves nothing selected (no port open)."""
        _fill_combo(self._midi_combo, [(port, port) for port in ports], current)

    def set_level(self, peak: float, clipping: bool = False):
        self._level_bar.setValue(int(peak * 100))
        self._clip_lbl.setStyleSheet(_CLIP_ON if clipping else _CLIP_OFF)

    def set_diagnostics(self, fps: float, overflows: int):
        self._diag_fps.setText(f'{fps:.0f} fps')
        self._diag_overflow.setText(str(overflows))

    def set_gain(self, gain: float):
        self._gain_slider.setValue(round(gain * 100))

    def set_smoothing(self, value: float):
        self._smooth_slider.setValue(round(value * 100))

    def set_fft_window(self, name: str):
        _select_data(self._window_combo, name)

    def set_log_level(self, level: str):
        _select_data(self._log_combo, level)

    def sync_sound_mode(self, is_on: bool):
        self._sm_btn.blockSignals(True)
        self._sm_btn.setChecked(is_on)
        self._sm_btn.setText('ON' if is_on else 'OFF')
        self._sm_btn.blockSignals(False)

    # ── Private signal handlers ───────────────────────────────────────────

    def _on_gain_changed(self, val: int):
        self._gain_readout.setText(f'{val}%')
        self.audio_gain_changed.emit(val / 100.0)

    def _on_smooth_changed(self, val: int):
        self._smooth_readout.setText(f'{val / 100.0:.1f}')
        self.smoothing_changed.emit(val / 100.0)
