"""In-memory stand-in for the UDP sockets used by pylzr.dmx.

Pass `FakeSocket` as a UdpSender's or UdpListener's socket_factory; nothing
touches the network. Every socket created is kept in `sockets`, and every datagram sent
by any of them is appended to `sent` as (payload, (host, port)), in order.

Module-wide knobs, restored by reset():
  route_from  local address connect() picks (what source_address() reports);
              None = no route to the host
  fail_next   errors the next sendto() calls raise, one per call
  bind_fails  errors the next bind() calls raise, one per call
  incoming    what the next recvfrom() calls return, oldest first, for
              whichever socket reads: (data, (ip, port)) datagrams, or
              OSErrors to raise. Empty = nothing waiting (BlockingIOError).
"""

import errno
import socket

sockets: list['FakeSocket'] = []
sent: list[tuple[bytes, tuple[str, int]]] = []
fail_next: list[OSError] = []
bind_fails: list[OSError] = []
incoming: list[tuple[bytes, tuple[str, int]] | OSError] = []
route_from: str | None = '10.201.6.50'

ANY_FREE_PORT = 50000     # the port a bind to port 0 gets


def reset():
    global route_from
    sockets.clear()
    sent.clear()
    fail_next.clear()
    bind_fails.clear()
    incoming.clear()
    route_from = '10.201.6.50'


def arrive(data: bytes, ip: str, port: int = 6454):
    """A datagram from ip:port, waiting to be received."""
    incoming.append((data, (ip, port)))


class FakeSocket:
    def __init__(self, family, kind):
        assert (family, kind) == (socket.AF_INET, socket.SOCK_DGRAM)
        self.sent: list[tuple[bytes, tuple[str, int]]] = []   # this socket's datagrams
        self.options: dict[tuple[int, int], int] = {}
        self.blocking = True
        self.closed = 0
        self.connected_to = None
        self.bound_to = None          # the address passed to bind()
        sockets.append(self)

    def setblocking(self, flag):
        self.blocking = flag

    def setsockopt(self, level, name, value):
        self.options[level, name] = value

    def connect(self, address):
        if route_from is None:
            raise OSError(errno.ENETUNREACH, 'Network is unreachable')
        self.connected_to = address

    def bind(self, address):
        if bind_fails:
            raise bind_fails.pop(0)
        self.bound_to = address

    def getsockname(self):
        if self.bound_to is not None:
            host, port = self.bound_to
            return (host or '0.0.0.0', port or ANY_FREE_PORT)
        return (route_from, 50000)

    def recvfrom(self, bufsize):
        if not incoming:
            raise BlockingIOError(errno.EWOULDBLOCK, 'would block')
        item = incoming.pop(0)
        if isinstance(item, OSError):
            raise item
        data, address = item
        return bytes(data)[:bufsize], address

    def sendto(self, data, address):
        if fail_next:
            raise fail_next.pop(0)
        item = (bytes(data), address)
        self.sent.append(item)
        sent.append(item)
        return len(data)

    def close(self):
        self.closed += 1
