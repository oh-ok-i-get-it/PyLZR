import socket
from collections.abc import Callable, Iterable

from PyQt5.QtCore import QObject, QTimer, pyqtSignal
from PyQt5.QtNetwork import QAbstractSocket, QNetworkInterface

from ..core.app_logger import get_logger
from .artnet import ARTNET_PORT, PollReply, build_artpoll, parse_artpollreply
from .udp    import UdpListener, describe_error

log = get_logger('dmx')

SEARCH_SECONDS = 2.0
_DRAIN_MS      = 50       # how often waiting replies are read


def local_broadcasts() -> list[str]:
    """The IPv4 broadcast address of each network this computer is on (e.g.
    10.255.255.255 for the Art-Net cable), skipping loopback and interfaces
    that are down."""
    found = []
    for interface in QNetworkInterface.allInterfaces():
        flags = interface.flags()
        if not (flags & QNetworkInterface.IsUp and flags & QNetworkInterface.IsRunning) \
                or flags & QNetworkInterface.IsLoopBack:
            continue
        for entry in interface.addressEntries():
            broadcast = entry.broadcast()
            if entry.ip().protocol() == QAbstractSocket.IPv4Protocol and not broadcast.isNull():
                address = broadcast.toString()
                if address not in found:
                    found.append(address)
    return found


class NodeDiscovery(QObject):
    """Finds Art-Net nodes and hears their answers, with ArtPoll.

    One per app: it owns the socket listening on the Art-Net port, which is
    opened the first time it's needed (search() or ping()), so a firewall
    prompt only ever appears then. Everything runs on the GUI thread; waiting
    replies are read every 50 ms without blocking.

    search() asks every network (each local broadcast address, plus
    extra_targets such as the configured node) and collects answers for a
    couple of seconds, then emits search_finished(list of PollReply), one per
    node reply (ip, bind index). ping(ip) asks one node. Every valid reply,
    from a search or a ping, is emitted as reply_received(PollReply);
    anything else arriving on the port (our own polls heard back, other
    Art-Net traffic) is ignored.

    socket_factory and broadcasts (a function returning broadcast addresses)
    are injectable so tests never touch the network.
    """

    reply_received  = pyqtSignal(object)    # PollReply
    search_finished = pyqtSignal(list)      # [PollReply]

    def __init__(self, parent: QObject | None = None,
                 socket_factory: Callable[..., socket.socket] = socket.socket,
                 broadcasts: Callable[[], Iterable[str]] | None = None):
        super().__init__(parent)
        self._socket_factory = socket_factory
        self._broadcasts = broadcasts or local_broadcasts
        self._listener: UdpListener | None = None
        self._found: dict[tuple[str, int], PollReply] | None = None   # None: not searching
        self._warned = False
        self._closed = False

        self._drain_timer = QTimer(self)
        self._drain_timer.setInterval(_DRAIN_MS)
        self._drain_timer.timeout.connect(self._drain)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._finish_search)

    @property
    def searching(self) -> bool:
        return self._found is not None

    def search(self, extra_targets: Iterable[str] = (), seconds: float = SEARCH_SECONDS) -> bool:
        """Poll every network and the extra_targets; search_finished follows
        after `seconds`. Returns False (and does nothing) if a search is
        already running."""
        self._check_open()
        if self.searching:
            return False
        self._found = {}
        targets = dict.fromkeys([*self._broadcasts(), *extra_targets])   # in order, once each
        for target in targets:
            self._poll(target)
        self._search_timer.start(round(seconds * 1000))
        return True

    def ping(self, ip: str):
        """Ask one node to answer (its reply comes as reply_received)."""
        self._check_open()
        self._poll(ip)

    def close(self):
        """Stop listening and release the socket. A running search ends
        without search_finished. Safe to call twice."""
        if self._closed:
            return
        self._closed = True
        self._drain_timer.stop()
        self._search_timer.stop()
        self._found = None
        if self._listener is not None:
            self._listener.close()

    # ── Internals ───────────────────────────────────────────────────────

    def _check_open(self):
        if self._closed:
            raise RuntimeError('NodeDiscovery is closed')

    def _poll(self, target: str):
        listener = self._open_listener()
        if listener is not None and not listener.send(build_artpoll(), target, ARTNET_PORT):
            log.debug(f'DMX: ArtPoll to {target} not sent: {listener.last_error or "send buffer full"}')

    def _open_listener(self) -> UdpListener | None:
        if self._listener is None:
            try:
                self._listener = UdpListener(ARTNET_PORT, socket_factory=self._socket_factory)
            except OSError as e:
                if not self._warned:
                    self._warned = True
                    log.warning(f'DMX: cannot listen for Art-Net nodes ({describe_error(e)}), '
                                'so nodes can\'t be found or confirmed; DMX output still works')
                return None
            if self._listener.fallback:
                log.warning(f'DMX: another program is using the Art-Net port ({ARTNET_PORT}), so some '
                            'nodes may not be found or confirmed. Close other Art-Net software if so.')
            self._drain_timer.start()
        return self._listener

    def _drain(self):
        for data, sender_ip in self._listener.receive():
            reply = parse_artpollreply(data, sender_ip)
            if reply is None:
                continue
            if self._found is not None:
                self._found[reply.ip, reply.bind_index] = reply     # a repeat replaces the older one
            self.reply_received.emit(reply)

    def _finish_search(self):
        if self._listener is not None:
            self._drain()                       # anything that arrived since the last read
        found, self._found = list(self._found.values()), None
        self.search_finished.emit(found)
