from collections.abc import Sequence

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QPushButton,
)
from PyQt5.QtCore import Qt, pyqtSignal, QSignalBlocker, QSize
from . import style, theme
from .widgets import Card, IndicatorTile, ValueLabel, set_role
from ..core import (
    CUTOFF_SLIDER_MAX,
    AVG_COUNT_RATE_DEFAULT, AVG_COUNT_RATE_MIN, AVG_COUNT_RATE_MAX,
    DEFAULT_LOW_THRESHOLDS, DEFAULT_HIGH_THRESHOLDS,
)

# Looks come from style roles (gui/style.py): 'sound-mode', 'toolbar-button', 'status',
# and the gui/widgets.py building blocks (Card, IndicatorTile, ValueLabel)
_SMALL_TILE = (38, 40)      # DM, CNT
_BIG_TILE   = (54, 52)      # LOW, HIGH


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
        root.setContentsMargins(0, 0, 0, 0)     # the main window sets the outer margin
        root.setSpacing(theme.GAP)

        # ── Top row: avg-rate slider | sound mode button | mode displays ─
        top_row = QHBoxLayout()
        top_row.setSpacing(theme.GAP)

        # Avg-rate slider (compact fixed width), value beside it
        rate_card = Card('AVGS CALC RATE', body=QHBoxLayout(), margins=(12, 9, 12, 9))
        rate_card.setMaximumWidth(200)
        rate_card.setFixedHeight(theme.TOP_ROW_H)      # sets the top row's height; the rest centre in it
        rate_card.body.setSpacing(8)
        self._count_label = ValueLabel(str(AVG_COUNT_RATE_DEFAULT))
        self._count_slider = QSlider(Qt.Horizontal)
        self._count_slider.setRange(AVG_COUNT_RATE_MIN, AVG_COUNT_RATE_MAX)
        self._count_slider.setValue(AVG_COUNT_RATE_DEFAULT)
        self._count_slider.setTickInterval(5)
        self._count_slider.setTickPosition(QSlider.TicksBelow)
        self._count_slider.valueChanged.connect(self._on_count_rate)
        rate_card.addWidget(self._count_slider, stretch=1)
        rate_card.addWidget(self._count_label)

        # Sound mode toggle button: dark tile when off; green tint, border and lit dot (its icon) when on
        self._sm_button = QPushButton('Sound Mode: OFF')
        self._sm_button.setCheckable(True)
        self._sm_button.setFixedHeight(52)
        self._sm_button.setMinimumWidth(160)
        set_role(self._sm_button, 'sound-mode')
        self._sm_button.setIcon(style.status_dot_icon(theme.DISABLED, theme.OK))
        self._sm_button.setIconSize(QSize(16, 16))
        self._sm_button.clicked.connect(lambda: self.sound_mode_toggled.emit())

        # Dual mode + count displays (small, muted — right of button)
        self._dm_display       = self._make_tile('DM\n—',  'neutral', _SMALL_TILE)
        self._dm_count_display = self._make_tile('CNT\n—', 'neutral', _SMALL_TILE)

        # Current sound mode index displays (LOW / HIGH)
        self._low_mode_display  = self._make_tile('LOW\n—',  'low',  _BIG_TILE)
        self._high_mode_display = self._make_tile('HIGH\n—', 'high', _BIG_TILE)

        top_row.addWidget(rate_card)
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
        set_role(self.gear_button, 'toolbar-button')    # icon only; accent while settings are open
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
        cutoff_row.setSpacing(theme.GAP)

        for band, title in (('low', 'LOW CUTOFFS'), ('high', 'HIGH CUTOFFS')):
            cutoffs = self._cutoffs[band]
            card = Card(title)
            card.body.setSpacing(2)
            for mode in range(3):
                name = 'Quiet' if mode == 0 else f'Mode {mode}'
                lbl = ValueLabel(f'{name}: {cutoffs[mode]}')
                sld = QSlider(Qt.Horizontal)
                sld.setRange(0, CUTOFF_SLIDER_MAX)
                sld.setValue(cutoffs[mode])
                sld.valueChanged.connect(lambda v, b=band, m=mode: self._on_cutoff(b, m, v))
                card.addWidget(lbl)
                card.addWidget(sld)
                self._cutoff_labels[band].append(lbl)
                self._cutoff_sliders[band].append(sld)
            cutoff_row.addWidget(card)

        root.addLayout(cutoff_row)

        # ── Status label ──────────────────────────────────────────────────
        self.status_label = QLabel('Press any key')
        set_role(self.status_label, 'status')
        root.addWidget(self.status_label)

        self.setLayout(root)

    @staticmethod
    def _make_tile(text: str, tone: str, size: tuple[int, int]) -> IndicatorTile:
        """An indicator tile: small label over a number (bigger on the big tiles)."""
        big = size == _BIG_TILE
        tile = IndicatorTile(text, tone, value_size=theme.SIZE_NUMBER if big else theme.SIZE_BODY + 2)
        tile.setFixedSize(*size)
        return tile

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
