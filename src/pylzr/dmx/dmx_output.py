import ipaddress
import socket
from collections.abc import Callable, Sequence

from PyQt5.QtCore import QObject, QTimer, Qt, pyqtSignal

from ..core import DMX_CHANNELS, DMX_DEFAULT_NODE_IP, DMX_REFRESH_HZ
from ..core.app_logger import Tone, get_logger
from .artnet   import ARTNET_PORT, PortAddress, build_artdmx, next_sequence
from .udp      import UdpSender
from .universe import DMXUniverse

log = get_logger('dmx')

_BLACKOUT = bytes(DMX_CHANNELS)

# Address blocks that can't share a network segment. Packets for a node in
# one block leaving from an address in another went to a router, not down
# the node's cable (typically: cable unplugged, Wi-Fi still up).
_BLOCKS = [ipaddress.ip_network(n) for n in
           ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16', '127.0.0.0/8')]


def _block(address: str) -> ipaddress.IPv4Network | None:
    ip = ipaddress.IPv4Address(address)
    return next((net for net in _BLOCKS if ip in net), None)


class DMXOutput(QObject):
    """DMX over Art-Net to one node (a core.protocols.NoteOutput).

    Holds a DMXUniverse and, while started, sends it to the node
    DMX_REFRESH_HZ times a second (DMX is a continuous stream: the node and
    fixtures expect the whole frame over and over). Everything runs on the
    GUI thread; one send takes microseconds.

    start() / stop() control sending; stop() and close() send one blackout
    frame first, so the laser goes dark rather than holding its last look.
    set_test_values() / clear_test_values() drive the universe's override
    layer (the channel tester).

    status_changed(state, detail) is emitted only when either changes:
      'off'      not sending                         'Off'
      'sending'  packets leave towards the node      'via 10.201.6.50'
      'warning'  they leave from an address on a     'via 192.168.1.20 — check cable / IP'
                 different network (likely a router)
      'error'    the OS refused to send              'network unreachable'
    UDP has no acknowledgement, so 'sending' doesn't prove the node is there.

    press_note() accepts cues so DMX can stand in for MIDI; it does nothing
    until scenes exist (a later phase).
    """

    status_changed = pyqtSignal(str, str)   # state, detail

    def __init__(self, node_ip: str = DMX_DEFAULT_NODE_IP, port: PortAddress | None = None,
                 parent: QObject | None = None,
                 socket_factory: Callable[..., socket.socket] = socket.socket):
        """port: Net:SubNet:Universe (default 0:0:0). An invalid node_ip raises ValueError."""
        super().__init__(parent)
        self.universe = DMXUniverse()
        self.port = port or PortAddress()
        self._socket_factory = socket_factory
        self._sender = UdpSender(node_ip, ARTNET_PORT, socket_factory)
        self._sequence = 0
        self._ticks = 0
        self._source: str | None = None
        self._closed = False
        self.state, self.detail = 'off', 'Off'

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)   # steady frame spacing
        self._timer.setInterval(round(1000 / DMX_REFRESH_HZ))
        self._timer.timeout.connect(self._tick)

    @property
    def node_ip(self) -> str:
        return self._sender.host

    @property
    def active(self) -> bool:
        return self._timer.isActive()

    # ── Lifecycle ───────────────────────────────────────────────────────

    def configure(self, node_ip: str, port: PortAddress) -> bool:
        """Send to a different node / universe. While active, the old target
        is blacked out first. An invalid IP is rejected (returns False) and
        nothing changes."""
        try:
            sender = UdpSender(node_ip, ARTNET_PORT, self._socket_factory)
        except ValueError:
            log.error(f'DMX: "{node_ip}" is not an IPv4 address')
            return False
        if self.active:
            self._send(_BLACKOUT)
        self._sender.close()
        self._sender, self.port = sender, port
        log.info(f'DMX: node {self.node_ip}, universe {port}', extra={'tone': Tone.MUTED})
        if self.active:
            self._check_route()
            self._tick()
        return True

    def start(self):
        if self._closed:
            raise RuntimeError('DMXOutput is closed')
        if self.active:
            return
        self._ticks = 0
        self._check_route()
        self._timer.start()
        self._tick()                    # first frame now, not one interval later

    def stop(self):
        """Stop sending, after one blackout frame. Does nothing if stopped."""
        if not self.active:
            return
        self._timer.stop()
        self._send(_BLACKOUT)
        self._set_status('off', 'Off')

    def close(self):
        """Stop (with blackout) and release the socket. Safe to call twice."""
        if self._closed:
            return
        self.stop()
        self._sender.close()
        self._closed = True

    # ── Content ─────────────────────────────────────────────────────────

    def set_test_values(self, start: int, values: Sequence[int]):
        """Manual channel values (the channel tester), shown over the show
        until clear_test_values()."""
        self.universe.set_overrides(start, values)

    def clear_test_values(self):
        self.universe.clear_overrides()

    def press_note(self, note: int):
        log.debug(f'DMX: cue {note} (no scenes yet — nothing to show)')

    # ── Sending ─────────────────────────────────────────────────────────

    def _tick(self):
        self._ticks += 1
        if self._ticks % DMX_REFRESH_HZ == 0:     # once a second: has the route changed?
            self._check_route()
        self._send(self.universe.frame())

    def _send(self, data: bytes):
        self._sequence = next_sequence(self._sequence)
        self._sender.send(build_artdmx(data, self.port, self._sequence))
        if self.active:
            self._update_status()

    def _check_route(self):
        self._source = self._sender.source_address()

    def _update_status(self):
        error, source = self._sender.last_error, self._source
        if error:
            self._set_status('error', error)
        elif source is None:
            self._set_status('error', 'no route to node')
        elif _block(source) != _block(self.node_ip):
            self._set_status('warning', f'via {source} — check cable / IP')
        else:
            self._set_status('sending', f'via {source}')

    def _set_status(self, state: str, detail: str):
        if (state, detail) == (self.state, self.detail):
            return
        changed_state = state != self.state
        self.state, self.detail = state, detail
        if changed_state:
            self._log_status()
        self.status_changed.emit(state, detail)

    def _log_status(self):
        target = f'{self.node_ip} (universe {self.port})'
        if self.state == 'sending':
            log.info(f'DMX: sending to {target} {self.detail}', extra={'tone': Tone.ON})
        elif self.state == 'warning':
            log.warning(f'DMX: packets for {target} leave via {self._source}, which is on a '
                        f"different network — is the node's cable plugged in and this computer's "
                        f'IP address set (see README)?')
        elif self.state == 'error':
            log.warning(f'DMX: cannot send to {target}: {self.detail}')
        else:
            log.info('DMX: output stopped (blackout sent)', extra={'tone': Tone.OFF})
