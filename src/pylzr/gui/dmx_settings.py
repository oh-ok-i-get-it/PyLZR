from collections.abc import Sequence

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLineEdit, QSpinBox, QAbstractSpinBox, QMenu,
)
from PyQt5.QtCore import QPoint, QRegularExpression, QSize, pyqtSignal
from PyQt5.QtGui import QRegularExpressionValidator

from ..core import DMX_DEFAULT_NODE_IP
from ..dmx import NodeChoice, is_ipv4
from . import style, theme
from .panel_style import INPUT_STYLE, SMALL_BUTTON_STYLE, label, pad, section

# Accepts what can still become an IPv4 address while typing; is_ipv4()
# decides when editing finishes.
_IPV4_TYPING = QRegularExpression(r'^(\d{1,3}(\.\d{0,3}){0,3})?$')

_TESTER_TIP_ON  = 'Open a window with one slider per DMX channel. Values go out live.'
_TESTER_TIP_OFF = 'Set Control Mode to DMX to use the channel tester.'
_FIND_TIP       = ('Look for Art-Net nodes on the network (takes 2 seconds), then pick one to fill in '
                   'its IP address and universe.')
_NONE_FOUND     = 'No Art-Net nodes answered (see the log)'

# The Find results menu uses the app-wide menu look (gui/style.py)


class DMXSettings(QWidget):
    """The DMX (ART-NET) section of the settings panel: the Art-Net node's
    IP address with a Find button, its universe (Net / Sub / Uni) and the
    channel tester button.

    Signals:
        node_changed(str, list) — node IP, [net, subnet, universe]; only
                                  valid values, only when they change
        tester_requested()      — 'Channel tester…' clicked
        find_requested()        — 'Find' clicked

    set_node() changes the fields as if the user had, emitting node_changed
    when the values change (used to restore saved settings). After a search,
    show_nodes() lists what was found under the Find button; picking a node
    goes through set_node().
    """

    node_changed     = pyqtSignal(str, list)
    tester_requested = pyqtSignal()
    find_requested   = pyqtSignal()

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

        self._find_btn = QPushButton('Find')
        self._find_btn.setFixedHeight(22)
        self._find_btn.setStyleSheet(SMALL_BUTTON_STYLE)
        self._find_btn.setIcon(style.icon('search', theme.TEXT_DIM, size=12))   # beside the text
        self._find_btn.setIconSize(QSize(12, 12))
        self._find_btn.setToolTip(_FIND_TIP)
        self._find_btn.clicked.connect(lambda: self.find_requested.emit())
        row.addWidget(self._find_btn)
        self._nodes_menu: QMenu | None = None
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

    def set_searching(self, searching: bool):
        """While a search runs, Find is disabled and shows '…'."""
        self._find_btn.setEnabled(not searching)
        self._find_btn.setText('…' if searching else 'Find')

    def show_nodes(self, choices: Sequence[NodeChoice]):
        """Drop down a menu of the nodes found under the Find button (never
        blocks). Choosing one sets the node; entries that can't be chosen
        are greyed out, with the reason in their label."""
        if self._nodes_menu is not None:
            self._nodes_menu.close()
            self._nodes_menu.deleteLater()
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        for choice in choices:
            action = menu.addAction(choice.label)
            action.setToolTip(choice.tooltip)        # Qt shows the label if this is empty
            action.setEnabled(choice.enabled)
            if choice.enabled:
                port = [choice.port.net, choice.port.subnet, choice.port.universe]
                action.triggered.connect(lambda _checked, ip=choice.ip, port=port: self.set_node(ip, port))
        if not choices:
            menu.addAction(_NONE_FOUND).setEnabled(False)
        self._nodes_menu = menu
        menu.popup(self._find_btn.mapToGlobal(QPoint(0, self._find_btn.height())))

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
