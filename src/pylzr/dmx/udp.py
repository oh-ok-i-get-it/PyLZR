import errno
import ipaddress
import socket
import sys
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


def is_ipv4(text: str) -> bool:
    """True for a dotted IPv4 address such as '10.201.6.100'."""
    try:
        ipaddress.IPv4Address(text)
        return True
    except ValueError:
        return False


def describe_error(e: OSError) -> str:
    return _ERROR_TEXT.get(e.errno) or e.strerror or str(e)


def _check_port(port: int, lowest: int = 1):
    if not lowest <= port < 65536:
        raise ValueError(f'port must be {lowest}–65535, got {port}')


class _UdpSocket:
    """What UdpSender and UdpListener share: one non-blocking IPv4 UDP socket
    with broadcast enabled, sends that never raise for network problems, and
    an idempotent close().

    A failed send returns False and records a short reason in `last_error`
    (cleared by the next successful send) — an unplugged cable must not crash
    the app. A momentarily full send buffer just drops that datagram (counted
    in `dropped`).
    """

    def __init__(self, sock: socket.socket):
        self._sock = sock
        self._sock.setblocking(False)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._closed = False
        self.last_error: str | None = None
        self.dropped = 0

    def _sendto(self, payload: bytes, address: tuple[str, int]) -> bool:
        if self._closed:
            raise RuntimeError(f'{type(self).__name__} is closed')
        try:
            self._sock.sendto(payload, address)
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


class UdpSender(_UdpSocket):
    """Sends UDP datagrams to one IPv4 host:port. Protocol-agnostic and
    Qt-free (Art-Net today; sACN could reuse it).

    send() never raises for network problems (see _UdpSocket). DMX resends
    the whole frame many times a second, so a dropped datagram doesn't matter.

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
        _check_port(port)
        self.port = port
        super().__init__(socket_factory(socket.AF_INET, socket.SOCK_DGRAM))
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
        return self._sendto(payload, (self.host, self.port))


class UdpListener(_UdpSocket):
    """A UDP socket bound to a local port, for protocols where the other side
    answers on a known port (Art-Net nodes reply to ArtPoll on 6454). Sends
    to any IPv4 host:port and receives without blocking. Protocol-agnostic
    and Qt-free; socket_factory is injectable, as for UdpSender.

    The port is bound on every network (bind_host '') with address reuse, so
    other programs listening on it (e.g. other Art-Net software) can keep
    running. If it's still taken, a free port is used instead and `fallback`
    is True: answers sent to the original port then reach only the other
    program. port 0 asks for any free port. Raises OSError if no port can be
    bound at all.
    """

    MAX_DATAGRAM = 2048     # bigger than any Art-Net packet

    def __init__(self, port: int, bind_host: str = '',
                 socket_factory: Callable[..., socket.socket] = socket.socket):
        _check_port(port, lowest=0)
        self.fallback = False
        try:
            sock = _bound_socket(socket_factory, bind_host, port)
        except OSError:
            if port == 0:
                raise
            sock = _bound_socket(socket_factory, bind_host, 0)
            self.fallback = True
        super().__init__(sock)
        self.port: int = sock.getsockname()[1]

    def send(self, payload: bytes, host: str, port: int) -> bool:
        """Send one datagram to host:port (an IPv4 address, or a broadcast
        address). Network problems are reported as for UdpSender."""
        _check_port(port)
        return self._sendto(payload, (str(ipaddress.IPv4Address(host)), port))

    def receive(self, limit: int = 64) -> list[tuple[bytes, str]]:
        """The datagrams waiting, oldest first, as (data, sender IP). Never
        blocks; at most `limit` per call, so a flood can't stall the caller.
        Network problems end the call early and are noted in `last_error`."""
        if self._closed:
            raise RuntimeError('UdpListener is closed')
        received = []
        for _ in range(limit):
            try:
                data, (ip, _port) = self._sock.recvfrom(self.MAX_DATAGRAM)
            except BlockingIOError:
                break
            except ConnectionResetError:
                # Windows reports an earlier send's "port unreachable" this way
                continue
            except OSError as e:
                self.last_error = describe_error(e)
                break
            received.append((data, ip))
        return received


def _bound_socket(socket_factory: Callable[..., socket.socket], host: str, port: int) -> socket.socket:
    sock = socket_factory(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        reuse_port = getattr(socket, 'SO_REUSEPORT', None)
        if sys.platform == 'darwin' and reuse_port is not None:   # macOS shares UDP ports only with this
            sock.setsockopt(socket.SOL_SOCKET, reuse_port, 1)
        sock.bind((host, port))
    except OSError:
        sock.close()
        raise
    return sock
