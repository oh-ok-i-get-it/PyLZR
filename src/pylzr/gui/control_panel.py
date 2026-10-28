from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QLabel, QSlider, QPushButton,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSignalBlocker
from . import theme
from ..core import (
    CUTOFF_SLIDER_MAX,
    AVG_COUNT_RATE_DEFAULT, AVG_COUNT_RATE_MIN, AVG_COUNT_RATE_MAX,
    DEFAULT_LOW_THRESHOLDS, DEFAULT_HIGH_THRESHOLDS,
)

_MODE_DISPLAY_STYLE = (
    'QLabel {{ background-color: #111; color: {color}; border: 1px solid #444;'
    ' font-weight: bold; font-size: 13px; padding: 2px 6px; }}'
)
_SMALL_DISPLAY_STYLE = (
    'QLabel {{ background-color: #0d0d0d; color: {color}; border: 1px solid #333;'
    ' font-size: 10px; padding: 1px 4px; }}'
)


class ControlPanel(QWidget):
    """Slider and button panel for runtime parameter control.

    Emits signals upward so main_window can route changes to the
    appropriate analysis/MIDI components without ControlPanel needing
    direct references to them.
    """

    count_rate_changed  = pyqtSignal(int)
    low_cutoff_changed  = pyqtSignal(int, int)  # (mode_index, value)
    high_cutoff_changed = pyqtSignal(int, int)  # (mode_index, value)
    sound_mode_toggled  = pyqtSignal()
    settings_toggled    = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._low_cutoffs  = list(DEFAULT_LOW_THRESHOLDS)
        self._high_cutoffs = list(DEFAULT_HIGH_THRESHOLDS)
        self._build()

    def _build(self):
        root = QVBoxLayout()
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── Top row: avg-rate slider | sound mode button | mode displays ─
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        # Avg-rate slider (compact fixed width)
        rate_group = QGroupBox('Avgs Calc Rate')
        rate_group.setMaximumWidth(200)
        rate_layout = QVBoxLayout()
        rate_layout.setContentsMargins(4, 2, 4, 2)
        rate_layout.setSpacing(1)
        self._count_label = QLabel(str(AVG_COUNT_RATE_DEFAULT))
        self._count_label.setStyleSheet('font-weight: bold;')
        count_slider = QSlider(Qt.Horizontal)
        count_slider.setRange(AVG_COUNT_RATE_MIN, AVG_COUNT_RATE_MAX)
        count_slider.setValue(AVG_COUNT_RATE_DEFAULT)
        count_slider.setTickInterval(5)
        count_slider.setTickPosition(QSlider.TicksBelow)
        count_slider.valueChanged.connect(self._on_count_rate)
        rate_layout.addWidget(count_slider)
        rate_layout.addWidget(self._count_label)
        rate_group.setLayout(rate_layout)

        # Sound mode toggle button
        self._sm_button = QPushButton('Sound Mode: OFF')
        self._sm_button.setCheckable(True)
        self._sm_button.setFixedHeight(52)
        self._sm_button.setMinimumWidth(160)
        self._sm_button.setStyleSheet(
            'QPushButton { background-color: #8b0000; color: white; font-weight: bold; font-size: 14px; border-radius: 4px; }'
            'QPushButton:checked { background-color: #006400; color: white; }'
        )
        self._sm_button.clicked.connect(lambda: self.sound_mode_toggled.emit())

        # Dual mode + count displays (small, muted — right of button)
        self._dm_display       = self._make_small_display('DM', '—', '#666')
        self._dm_count_display = self._make_small_display('CNT', '—', '#555')

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
        self.gear_button.setStyleSheet(
            'QPushButton {'
            '  background: transparent; color: #555; font-size: 17px;'
            '  border: none; border-radius: 4px;'
            '}'
            'QPushButton:hover { color: #c9d1d9; background: #1e1e1e; }'
            f'QPushButton:checked {{ color: {theme.ACCENT}; background: #1a1a1a; }}'
        )
        self.gear_button.clicked.connect(lambda: self.settings_toggled.emit())
        top_row.addWidget(self.gear_button)

        root.addLayout(top_row)

        # ── Cutoff row: low (left) | high (right) ────────────────────────
        cutoff_row = QHBoxLayout()
        cutoff_row.setSpacing(8)

        self._low_sliders  = []
        self._low_labels   = []
        self._high_sliders = []
        self._high_labels  = []

        for side, cutoffs, sliders_list, labels_list, callback in (
            ('Low Cutoffs',  self._low_cutoffs,  self._low_sliders,  self._low_labels,  self._on_low_cutoff),
            ('High Cutoffs', self._high_cutoffs, self._high_sliders, self._high_labels, self._on_high_cutoff),
        ):
            group = QGroupBox(side)
            glayout = QVBoxLayout()
            glayout.setContentsMargins(4, 4, 4, 4)
            glayout.setSpacing(2)
            for mode in range(3):
                name = 'Quiet' if mode == 0 else f'Mode {mode}'
                lbl = QLabel(f'{name}: {cutoffs[mode]}')
                sld = QSlider(Qt.Horizontal)
                sld.setRange(0, CUTOFF_SLIDER_MAX)
                sld.setValue(cutoffs[mode])
                sld.valueChanged.connect(lambda v, m=mode, cb=callback: cb(v, m))
                glayout.addWidget(lbl)
                glayout.addWidget(sld)
                labels_list.append(lbl)
                sliders_list.append(sld)
            group.setLayout(glayout)
            cutoff_row.addWidget(group)

        root.addLayout(cutoff_row)

        # ── Status label ──────────────────────────────────────────────────
        self.status_label = QLabel('Press any key')
        root.addWidget(self.status_label)

        self.setLayout(root)

    @staticmethod
    def _make_small_display(label: str, value: str, color: str) -> QLabel:
        lbl = QLabel(f'{label}\n{value}')
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setFixedSize(38, 40)
        lbl.setStyleSheet(_SMALL_DISPLAY_STYLE.format(color=color))
        return lbl

    @staticmethod
    def _make_mode_display(band: str, value: str, color: str) -> QLabel:
        lbl = QLabel(f'{band}\n{value}')
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setFixedSize(54, 52)
        lbl.setStyleSheet(_MODE_DISPLAY_STYLE.format(color=color))
        return lbl

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

    def _on_low_cutoff(self, val: int, mode: int):
        if mode == 0:
            val = min(val, self._low_cutoffs[1])
        elif mode == 1:
            val = max(val, self._low_cutoffs[0])
            val = min(val, self._low_cutoffs[2])
        else:
            val = max(val, self._low_cutoffs[1])
        sld = self._low_sliders[mode]
        if sld.value() != val:
            with QSignalBlocker(sld):
                sld.setValue(val)
        self._low_cutoffs[mode] = val
        name = 'Quiet' if mode == 0 else f'Mode {mode}'
        self._low_labels[mode].setText(f'{name}: {val}')
        self.low_cutoff_changed.emit(mode, val)

    def _on_high_cutoff(self, val: int, mode: int):
        if mode == 0:
            val = min(val, self._high_cutoffs[1])
        elif mode == 1:
            val = max(val, self._high_cutoffs[0])
            val = min(val, self._high_cutoffs[2])
        else:
            val = max(val, self._high_cutoffs[1])
        sld = self._high_sliders[mode]
        if sld.value() != val:
            with QSignalBlocker(sld):
                sld.setValue(val)
        self._high_cutoffs[mode] = val
        name = 'Quiet' if mode == 0 else f'Mode {mode}'
        self._high_labels[mode].setText(f'{name}: {val}')
        self.high_cutoff_changed.emit(mode, val)
