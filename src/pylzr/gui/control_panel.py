from collections.abc import Sequence

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QSlider, QPushButton,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSignalBlocker, QSize
from . import style, theme
from ..core import (
    CUTOFF_SLIDER_MAX,
    AVG_COUNT_RATE_DEFAULT, AVG_COUNT_RATE_MIN, AVG_COUNT_RATE_MAX,
    DEFAULT_LOW_THRESHOLDS, DEFAULT_HIGH_THRESHOLDS,
)

_TILE_BORDER = '#222222'

# Indicator tiles: two lines of mono text ('LOW\n2'), band colour on LOW / HIGH
_DISPLAY_STYLE = (
    'QLabel {{ background: ' + theme.CARD + '; color: {color};'
    ' border: 1px solid {border}; border-radius: ' + str(theme.RADIUS_CARD) + 'px;'
    ' font-family: "' + theme.MONO_FONT + '"; font-size: {size}px; font-weight: bold; }}'
)

# Sound Mode: a dark tile when off; green tint, border and lit dot (its icon) when on
_SM_STYLE = (
    f'QPushButton {{ background: {theme.CARD}; color: {theme.TEXT_DIM};'
    f' border: 1px solid #262626; border-radius: {theme.RADIUS_CARD}px;'
    f' font-size: {theme.SIZE_TITLE}px; font-weight: 600; padding: 0 12px; }}'
    'QPushButton:hover { border-color: #3a3a3a; }'
    f'QPushButton:checked {{ background: {style.mix(theme.OK, theme.BG, 0.09)};'
    f' color: {style.mix(theme.OK, "#ffffff", 0.5)}; border-color: {style.mix(theme.OK, theme.BG, 0.55)}; }}'
    f'QPushButton:checked:hover {{ border-color: {theme.OK}; }}'
)

# Gear: icon only; outlined on hover, accent while the settings panel is open
_GEAR_STYLE = (
    'QPushButton { background: transparent; border: 1px solid transparent;'
    f' border-radius: {theme.RADIUS}px; padding: 0; color: {theme.TEXT_DIM}; font-size: 17px; }}'
    f'QPushButton:hover {{ background: {theme.BUTTON}; border-color: {theme.BORDER_STRONG}; }}'
    f'QPushButton:checked {{ background: {style.mix(theme.ACCENT, theme.BG, 0.14)};'
    f' border-color: {theme.ACCENT}; color: {theme.ACCENT}; }}'
)

_LABEL_STYLE  = f'color: {theme.TEXT_DIM}; font-size: {theme.SIZE_LABEL}px; font-weight: normal;'
_STATUS_STYLE = f'color: {theme.TEXT_MUTED}; font-size: {theme.SIZE_LABEL}px;'
_VALUE_STYLE  = f'color: {theme.TEXT}; font-family: "{theme.MONO_FONT}"; font-size: {theme.SIZE_BODY}px; font-weight: bold;'


class ControlPanel(QWidget):
    """Slider and button panel for runtime parameter control.

    Emits signals upward so main_window can route changes to the
    appropriate analysis/MIDI components without ControlPanel needing
    direct references to them.
    """

    count_rate_changed = pyqtSignal(int)
    cutoff_changed     = pyqtSignal(str, int, int)  # (band 'low'|'high', mode_index, value)
    sound_mode_toggled  = pyqtSignal()
    settings_toggled    = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cutoffs = {'low': list(DEFAULT_LOW_THRESHOLDS), 'high': list(DEFAULT_HIGH_THRESHOLDS)}
        self._cutoff_sliders: dict[str, list[QSlider]] = {'low': [], 'high': []}
        self._cutoff_labels:  dict[str, list[QLabel]]  = {'low': [], 'high': []}
        self._build()

    def _build(self):
        root = QVBoxLayout()
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── Top row: avg-rate slider | sound mode button | mode displays ─
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        # Avg-rate slider (compact fixed width)
        rate_group = QGroupBox('AVGS CALC RATE')
        rate_group.setMaximumWidth(200)
        rate_layout = QHBoxLayout()           # value beside the slider
        rate_layout.setContentsMargins(2, 0, 2, 0)
        rate_layout.setSpacing(8)
        self._count_label = QLabel(str(AVG_COUNT_RATE_DEFAULT))
        self._count_label.setStyleSheet(_VALUE_STYLE)
        self._count_slider = QSlider(Qt.Horizontal)
        self._count_slider.setRange(AVG_COUNT_RATE_MIN, AVG_COUNT_RATE_MAX)
        self._count_slider.setValue(AVG_COUNT_RATE_DEFAULT)
        self._count_slider.setTickInterval(5)
        self._count_slider.setTickPosition(QSlider.TicksBelow)
        self._count_slider.valueChanged.connect(self._on_count_rate)
        rate_layout.addWidget(self._count_slider)
        rate_layout.addWidget(self._count_label)
        rate_group.setLayout(rate_layout)

        # Sound mode toggle button
        self._sm_button = QPushButton('Sound Mode: OFF')
        self._sm_button.setCheckable(True)
        self._sm_button.setFixedHeight(52)
        self._sm_button.setMinimumWidth(160)
        self._sm_button.setStyleSheet(_SM_STYLE)
        self._sm_button.setIcon(style.status_dot_icon(theme.DISABLED, theme.OK))
        self._sm_button.setIconSize(QSize(16, 16))
        self._sm_button.clicked.connect(lambda: self.sound_mode_toggled.emit())

        # Dual mode + count displays (small, muted — right of button)
        self._dm_display       = self._make_small_display('DM', '—', theme.TEXT_DIM)
        self._dm_count_display = self._make_small_display('CNT', '—', theme.TEXT_DIM)

        # Current sound mode index displays (LOW / HIGH)
        self._low_mode_display  = self._make_mode_display('LOW',  '—', theme.LOW_BAND)
        self._high_mode_display = self._make_mode_display('HIGH', '—', theme.HIGH_BAND)

        top_row.addWidget(rate_group)
        top_row.addWidget(self._sm_button)
        top_row.addWidget(self._dm_display)
        top_row.addWidget(self._dm_count_display)
        top_row.addWidget(self._low_mode_display)
        top_row.addWidget(self._high_mode_display)
        top_row.addStretch(1)

        # Gear / settings button — pinned to the far right of the top row
        self.gear_button = QPushButton('⚙')
        self.gear_button.setFixedSize(30, 30)
        self.gear_button.setCheckable(True)
        self.gear_button.setToolTip('Settings')
        self.gear_button.setStyleSheet(_GEAR_STYLE)
        gear_icon = style.icon('settings', theme.TEXT_DIM, on_color=theme.ACCENT)
        if not gear_icon.isNull():              # otherwise the ⚙ glyph stays
            self.gear_button.setIcon(gear_icon)
            self.gear_button.setIconSize(QSize(16, 16))
            self.gear_button.setText('')
        self.gear_button.clicked.connect(lambda: self.settings_toggled.emit())
        top_row.addWidget(self.gear_button)

        root.addLayout(top_row)

        # ── Cutoff row: low (left) | high (right) ────────────────────────
        cutoff_row = QHBoxLayout()
        cutoff_row.setSpacing(8)

        for band, title in (('low', 'LOW CUTOFFS'), ('high', 'HIGH CUTOFFS')):
            cutoffs = self._cutoffs[band]
            group = QGroupBox(title)
            glayout = QVBoxLayout()
            glayout.setContentsMargins(4, 4, 4, 4)
            glayout.setSpacing(2)
            for mode in range(3):
                name = 'Quiet' if mode == 0 else f'Mode {mode}'
                lbl = QLabel(f'{name}: {cutoffs[mode]}')
                lbl.setStyleSheet(_LABEL_STYLE)
                sld = QSlider(Qt.Horizontal)
                sld.setRange(0, CUTOFF_SLIDER_MAX)
                sld.setValue(cutoffs[mode])
                sld.valueChanged.connect(lambda v, b=band, m=mode: self._on_cutoff(b, m, v))
                glayout.addWidget(lbl)
                glayout.addWidget(sld)
                self._cutoff_labels[band].append(lbl)
                self._cutoff_sliders[band].append(sld)
            group.setLayout(glayout)
            cutoff_row.addWidget(group)

        root.addLayout(cutoff_row)

        # ── Status label ──────────────────────────────────────────────────
        self.status_label = QLabel('Press any key')
        self.status_label.setStyleSheet(_STATUS_STYLE)
        root.addWidget(self.status_label)

        self.setLayout(root)

    @staticmethod
    def _make_small_display(label: str, value: str, color: str) -> QLabel:
        lbl = QLabel(f'{label}\n{value}')
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setFixedSize(38, 40)
        lbl.setStyleSheet(_DISPLAY_STYLE.format(color=color, border=_TILE_BORDER, size=11))
        return lbl

    @staticmethod
    def _make_mode_display(band: str, value: str, color: str) -> QLabel:
        lbl = QLabel(f'{band}\n{value}')
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setFixedSize(54, 52)
        lbl.setStyleSheet(_DISPLAY_STYLE.format(color=color, border=style.mix(color, _TILE_BORDER, 0.35), size=15))
        return lbl

    def set_count_rate(self, frames: int):
        """As if the user moved the slider (emits count_rate_changed if it changes)."""
        self._count_slider.setValue(frames)

    def cutoffs(self, band: str) -> list[int]:
        return list(self._cutoffs[band])

    def set_cutoffs(self, band: str, values: Sequence[int]):
        """Set all three cutoffs of a band at once and emit cutoff_changed for
        each. Values are put in order first, so they can't clamp each other."""
        values = sorted(min(max(int(v), 0), CUTOFF_SLIDER_MAX) for v in values)
        self._cutoffs[band] = values
        for mode, val in enumerate(values):
            with QSignalBlocker(self._cutoff_sliders[band][mode]):
                self._cutoff_sliders[band][mode].setValue(val)
            self._on_cutoff(band, mode, val)

    def sync_sound_mode(self, is_on: bool):
        self._sm_button.setChecked(is_on)
        self._sm_button.setText('Sound Mode: ON' if is_on else 'Sound Mode: OFF')

    def sync_gear(self, is_open: bool):
        self.gear_button.setChecked(is_open)

    def update_sound_modes(self, low_mode: int, high_mode: int):
        self._low_mode_display.setText(f'LOW\n{"—" if low_mode < 0 else low_mode}')
        self._high_mode_display.setText(f'HIGH\n{"—" if high_mode < 0 else high_mode}')

    def update_dual_mode(self, dm_mode: int, dm_count: int):
        self._dm_display.setText(f'DM\n{dm_mode}')
        self._dm_count_display.setText(f'CNT\n{dm_count}')

    def _on_count_rate(self, val: int):
        self._count_label.setText(str(val))
        self.count_rate_changed.emit(val)

    def _on_cutoff(self, band: str, mode: int, val: int):
        """Clamp so Quiet <= Mode 1 <= Mode 2, then show and emit the value."""
        cutoffs = self._cutoffs[band]
        lower = cutoffs[mode - 1] if mode > 0 else 0
        upper = cutoffs[mode + 1] if mode < 2 else CUTOFF_SLIDER_MAX
        val = min(max(val, lower), upper)
        sld = self._cutoff_sliders[band][mode]
        if sld.value() != val:
            with QSignalBlocker(sld):
                sld.setValue(val)
        cutoffs[mode] = val
        name = 'Quiet' if mode == 0 else f'Mode {mode}'
        self._cutoff_labels[band][mode].setText(f'{name}: {val}')
        self.cutoff_changed.emit(band, mode, val)
