from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QSlider, QSpinBox,
    QPushButton, QAbstractSpinBox,
)
from PyQt5.QtCore import Qt, pyqtSignal

from ..core import DMX_CHANNELS
from . import style, theme

MAX_SHOWN     = 32   # sliders shown at once
DEFAULT_SHOWN = 16

# The faders use the app-wide slider look (gui/style.py); the warning is an amber strip
_WINDOW_STYLE = (
    f'QWidget#DMXTester {{ background: {theme.BG}; }}'
    f'QLabel {{ color: {theme.TEXT_DIM}; font-size: {theme.SIZE_LABEL}px; }}'
    'QLabel#Warning {'
    f'  color: {theme.WARN}; background: {style.mix(theme.WARN, theme.BG, 0.07)};'
    f'  border: 1px solid {style.mix(theme.WARN, theme.BG, 0.25)}; border-radius: {theme.RADIUS}px;'
    '  padding: 5px 10px;'
    '}'
    f'QLabel#Channel {{ color: {theme.TEXT_DIM}; font-family: "{theme.MONO_FONT}"; font-weight: bold; }}'
    'QSpinBox {'
    f'  background: {theme.RAISED}; color: {theme.TEXT};'
    f'  border: 1px solid {theme.BORDER_STRONG}; border-radius: {theme.RADIUS}px;'
    f'  padding: 1px 3px; font-family: "{theme.MONO_FONT}"; font-size: {theme.SIZE_LABEL}px;'
    '}'
    f'QSpinBox:hover, QSpinBox:focus {{ border-color: {theme.ACCENT}; }}'
    'QPushButton {'
    f'  background: {theme.BUTTON}; color: {theme.TEXT}; font-size: {theme.SIZE_LABEL}px;'
    f'  border: 1px solid {theme.BORDER_STRONG}; border-radius: {theme.RADIUS}px; padding: 3px 10px;'
    '}'
    f'QPushButton:hover {{ border-color: {theme.ACCENT}; }}'
    f'QPushButton:pressed {{ background: {theme.RAISED}; }}'
)


def _number_box(low: int, high: int, value: int, width: int) -> QSpinBox:
    box = QSpinBox()
    box.setRange(low, high)
    box.setValue(value)
    box.setButtonSymbols(QAbstractSpinBox.NoButtons)
    box.setAlignment(Qt.AlignCenter)
    box.setFixedWidth(width)
    return box


class DMXTesterWindow(QWidget):
    """A small tool window with one slider per DMX channel, for finding out
    what a fixture's channels do.

    Knows nothing about DMX output: it only reports what the sliders show.

    Signals:
        channels_changed(int, list) — first channel (1–512) and the values
                                      (0–255) of every shown channel; emitted
                                      on any change, and when shown
        closed()                    — the window was closed (values are then
                                      back at 0 for next time)

    Changing the start channel puts every slider back to 0, so values never
    jump onto channels you haven't looked at. Changing how many channels
    are shown keeps the values of the ones still shown.
    """

    channels_changed = pyqtSignal(int, list)
    closed           = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, Qt.Tool)
        self.setObjectName('DMXTester')
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(_WINDOW_STYLE)
        self.setWindowTitle('DMX Channel Tester')
        style.dark_title_bar(self)                 # Windows only; no-op elsewhere

        self._sliders: list[QSlider] = []
        self._value_boxes: list[QSpinBox] = []
        self._channel_labels: list[QLabel] = []

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)
        root.addLayout(self._build_header())

        warning = QLabel('Values go out live. Keep the laser aimed safely before moving a slider.')
        warning.setObjectName('Warning')
        root.addWidget(warning)

        self._strip = QGridLayout()
        self._strip.setHorizontalSpacing(4)
        self._strip.setVerticalSpacing(4)
        root.addLayout(self._strip, stretch=1)

        self._rebuild_strip(DEFAULT_SHOWN)
        self.resize(self.sizeHint().width(), 320)

    # ── Layout ────────────────────────────────────────────────────────────

    def _build_header(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)

        self._start_box = _number_box(1, DMX_CHANNELS - DEFAULT_SHOWN + 1, 1, 44)
        self._start_box.setToolTip('First channel shown (1–512). Changing it puts every slider back to 0.')
        self._start_box.valueChanged.connect(self._on_start_changed)

        self._count_box = _number_box(1, MAX_SHOWN, DEFAULT_SHOWN, 36)
        self._count_box.setToolTip(f'How many channels to show (1–{MAX_SHOWN})')
        self._count_box.valueChanged.connect(self._on_count_changed)

        self._zero_btn = QPushButton('All 0')
        self._zero_btn.setToolTip('Every shown channel to 0')
        self._zero_btn.clicked.connect(self.zero_all)

        row.addWidget(QLabel('Start channel'))
        row.addWidget(self._start_box)
        row.addSpacing(8)
        row.addWidget(QLabel('Channels'))
        row.addWidget(self._count_box)
        row.addStretch(1)
        row.addWidget(self._zero_btn)
        return row

    def _rebuild_strip(self, count: int):
        """Show `count` channel columns, keeping the values of the first ones."""
        kept = self.values[:count]
        for widget in (*self._channel_labels, *self._sliders, *self._value_boxes):
            self._strip.removeWidget(widget)
            widget.deleteLater()
        self._channel_labels, self._sliders, self._value_boxes = [], [], []

        for col in range(count):
            value = kept[col] if col < len(kept) else 0

            label = QLabel()
            label.setObjectName('Channel')
            label.setAlignment(Qt.AlignCenter)

            slider = QSlider(Qt.Vertical)
            slider.setRange(0, 255)
            slider.setPageStep(16)
            slider.setValue(value)
            slider.setMinimumHeight(140)

            box = _number_box(0, 255, value, 36)

            slider.valueChanged.connect(lambda v, b=box: self._on_slider(b, v))
            box.valueChanged.connect(slider.setValue)    # slider then updates and emits

            self._strip.addWidget(label,  0, col, Qt.AlignHCenter)
            self._strip.addWidget(slider, 1, col, Qt.AlignHCenter)
            self._strip.addWidget(box,    2, col, Qt.AlignHCenter)
            self._channel_labels.append(label)
            self._sliders.append(slider)
            self._value_boxes.append(box)
        self._renumber()

    def _renumber(self):
        for i, label in enumerate(self._channel_labels):
            label.setText(str(self.start + i))

    # ── State ─────────────────────────────────────────────────────────────

    @property
    def start(self) -> int:
        return self._start_box.value()

    @property
    def count(self) -> int:
        return len(self._sliders)

    @property
    def values(self) -> list[int]:
        return [slider.value() for slider in self._sliders]

    def zero_all(self):
        self._set_all_silently(0)
        self._emit()

    def _set_all_silently(self, value: int):
        for slider, box in zip(self._sliders, self._value_boxes, strict=True):
            for widget in (slider, box):
                widget.blockSignals(True)
                widget.setValue(value)
                widget.blockSignals(False)

    def _emit(self):
        self.channels_changed.emit(self.start, self.values)

    # ── Handlers ──────────────────────────────────────────────────────────

    def _on_slider(self, box: QSpinBox, value: int):
        box.setValue(value)             # its echo back to the slider is a no-op (same value)
        self._emit()

    def _on_start_changed(self, start: int):
        self._count_box.setMaximum(min(MAX_SHOWN, DMX_CHANNELS - start + 1))
        self._set_all_silently(0)
        self._renumber()
        self._emit()

    def _on_count_changed(self, count: int):
        self._start_box.setMaximum(DMX_CHANNELS - count + 1)
        self._rebuild_strip(count)
        self._emit()

    # ── Qt events ─────────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        self._emit()                    # whoever listens starts from what's shown

    def closeEvent(self, event):
        self._set_all_silently(0)       # opening again starts dark
        super().closeEvent(event)
        self.closed.emit()
