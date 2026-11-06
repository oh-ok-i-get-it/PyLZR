from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QSpinBox, QAbstractSpinBox,
)
from PyQt5.QtCore import QRegularExpression, pyqtSignal
from PyQt5.QtGui import QRegularExpressionValidator

from ..core import DMX_DEFAULT_NODE_IP
from ..dmx import is_ipv4
from .panel_style import INPUT_STYLE, SMALL_BUTTON_STYLE, label, pad, section

# Accepts what can still become an IPv4 address while typing; is_ipv4()
# decides when editing finishes.
_IPV4_TYPING = QRegularExpression(r'^(\d{1,3}(\.\d{0,3}){0,3})?$')

_TESTER_TIP_ON  = 'Open a window with one slider per DMX channel. Values go out live.'
_TESTER_TIP_OFF = 'Set Control Mode to DMX to use the channel tester.'


class DMXSettings(QWidget):
    """The DMX (ART-NET) section of the settings panel: the Art-Net node's
    IP address, its universe (Net / Sub / Uni) and the channel tester button.

    Signals:
        node_changed(str, list) — node IP, [net, subnet, universe]; only
                                  valid values, only when they change
        tester_requested()      — 'Channel tester…' clicked

    set_node() changes the fields as if the user had, emitting node_changed
    when the values change (used to restore saved settings).
    """

    node_changed     = pyqtSignal(str, list)
    tester_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._build())

    def _build(self) -> QWidget:
        """Full-width Art-Net row: node address, universe, channel tester."""
        v = QVBoxLayout()
        v.setSpacing(6)
        v.addWidget(section('DMX (ART-NET)'))

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(5)

        self._node = (DMX_DEFAULT_NODE_IP, [0, 0, 0])   # last valid values emitted

        self._node_ip_edit = QLineEdit(DMX_DEFAULT_NODE_IP)
        self._node_ip_edit.setValidator(QRegularExpressionValidator(_IPV4_TYPING))
        self._node_ip_edit.setFixedWidth(104)
        self._node_ip_edit.setStyleSheet(INPUT_STYLE)
        self._node_ip_edit.setToolTip("The Art-Net node's IP address (CR011R factory default: "
                                      f'{DMX_DEFAULT_NODE_IP})')
        self._node_ip_edit.editingFinished.connect(self._on_node_ip_edited)
        row.addWidget(label('Node IP'))
        row.addWidget(self._node_ip_edit)
        row.addSpacing(6)

        self._port_spins = []
        for text, top, tip in (('Net', 127, 'Art-Net Net (0–127)'),
                               ('Sub', 15, 'Art-Net SubNet (0–15)'),
                               ('Uni', 15, 'Art-Net Universe (0–15)')):
            spin = QSpinBox()
            spin.setRange(0, top)
            spin.setButtonSymbols(QAbstractSpinBox.NoButtons)
            spin.setFixedWidth(34)
            spin.setStyleSheet(INPUT_STYLE)
            spin.setToolTip(f'{tip} — as set in the node\'s menu. Type, scroll or use the arrow keys.')
            spin.valueChanged.connect(lambda _value: self._emit_node())
            row.addWidget(label(text))
            row.addWidget(spin)
            self._port_spins.append(spin)
        row.addStretch(1)

        self._tester_btn = QPushButton('Channel tester…')
        self._tester_btn.setFixedHeight(22)
        self._tester_btn.setStyleSheet(SMALL_BUTTON_STYLE)
        self._tester_btn.clicked.connect(lambda: self.tester_requested.emit())
        row.addWidget(self._tester_btn)
        self.set_tester_enabled(False)

        v.addLayout(row)
        return pad(v, t=8, b=10)

    # ── Public setters ────────────────────────────────────────────────────

    def set_node(self, ip: str, port_address: list[int]):
        """Show a node IP and [net, subnet, universe]; emits node_changed
        if they differ from the current values. An invalid IP is ignored."""
        if is_ipv4(ip):
            self._node_ip_edit.setText(ip)
        for spin, value in zip(self._port_spins, port_address, strict=True):
            spin.blockSignals(True)          # one emit for all three, below
            spin.setValue(value)
            spin.blockSignals(False)
        self._emit_node()

    def set_tester_enabled(self, enabled: bool):
        self._tester_btn.setEnabled(enabled)
        self._tester_btn.setToolTip(_TESTER_TIP_ON if enabled else _TESTER_TIP_OFF)

    # ── Private signal handlers ───────────────────────────────────────────

    def _on_node_ip_edited(self):
        if is_ipv4(self._node_ip_edit.text()):
            self._emit_node()
        else:                                # e.g. '10.201.6' — put the last good address back
            self._node_ip_edit.setText(self._node[0])

    def _emit_node(self):
        """Emit node_changed if the shown values differ from the last
        emitted ones (an IP still being typed counts as unchanged)."""
        text = self._node_ip_edit.text()
        ip = text if is_ipv4(text) else self._node[0]
        node = (ip, [spin.value() for spin in self._port_spins])
        if node != self._node:
            self._node = node
            self.node_changed.emit(*node)
