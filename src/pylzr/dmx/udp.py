import errno
import ipaddress
import socket
from collections.abc import Callable

# Friendly names for the errors a direct-cabled node usually produces.
# (On Windows, Python's errno values are the WSA socket codes, e.g.
# ENETUNREACH == 10051, so one table serves every OS.)
_ERROR_TEXT = {
    errno.ENETUNREACH:   'network unreachable',
    errno.EHOSTUNREACH:  'host unreachable',
    errno.ENETDOWN:      'network is down',
    errno.EADDRNOTAVAIL: 'address not available',
}


def describe_error(e: OSError) -> str:
    return _ERROR_TEXT.get(e.errno) or e.strerror or str(e)


class UdpSender:
    """Sends UDP datagrams to one IPv4 host:port. Protocol-agnostic and
    Qt-free (Art-Net today; sACN could reuse it).

    send() never raises for network problems — an unplugged cable must not
    crash the app. It returns False and records a short reason in
    `last_error` (cleared by the next successful send). A momentarily full
    send buffer just drops that datagram (counted in `dropped`); DMX resends
    the whole frame many times a second anyway.

    Note that a successful send doesn't mean the datagram reached the node:
    with the node's cable unplugged but Wi-Fi up, the OS happily routes it
    to the Wi-Fi router instead. source_address() shows which local address
    the OS would use, which exposes that case.

    Broadcast is enabled, so a broadcast address (e.g. 10.255.255.255) works
    too. socket_factory is injectable so tests can capture packets without
    touching the network.
    """

    def __init__(self, host: str, port: int,
                 socket_factory: Callable[..., socket.socket] = socket.socket):
        self.host = str(ipaddress.IPv4Address(host))   # ValueError unless dotted IPv4
        if not 0 < port < 65536:
            raise ValueError(f'port must be 1–65535, got {port}')
        self.port = port
        self.last_error: str | None = None
        self.dropped = 0

        self._sock = socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setblocking(False)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._closed = False
        self._socket_factory = socket_factory

    def source_address(self) -> str | None:
        """The local IPv4 address the OS would send from to reach host, or
        None if there's no route. Sends nothing (connect() on a UDP socket
        only picks a route)."""
        probe = self._socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect((self.host, self.port))
            return probe.getsockname()[0]
        except OSError:
            return None
        finally:
            probe.close()

    def send(self, payload: bytes) -> bool:
        """Send one datagram. True if it was handed to the network stack
        (UDP has no delivery confirmation)."""
        if self._closed:
            raise RuntimeError('UdpSender is closed')
        try:
            self._sock.sendto(payload, (self.host, self.port))
        except BlockingIOError:
            self.dropped += 1
            return False
        except OSError as e:
            self.last_error = describe_error(e)
            return False
        self.last_error = None
        return True

    def close(self):
        """Release the socket. Safe to call twice."""
        if not self._closed:
            self._closed = True
            self._sock.close()
