"""In-memory stand-in for the UDP sockets used by pylzr.dmx.

Pass `FakeSocket` as a UdpSender's socket_factory; nothing touches the
network. Every socket created is kept in `sockets`, and every datagram sent
by any of them is appended to `sent` as (payload, (host, port)), in order.

Module-wide knobs, restored by reset():
  route_from  local address connect() picks (what source_address() reports);
              None = no route to the host
  fail_next   errors the next sendto() calls raise, one per call
"""

import errno
import socket

sockets: list['FakeSocket'] = []
sent: list[tuple[bytes, tuple[str, int]]] = []
fail_next: list[OSError] = []
route_from: str | None = '10.201.6.50'


def reset():
    global route_from
    sockets.clear()
    sent.clear()
    fail_next.clear()
    route_from = '10.201.6.50'


class FakeSocket:
    def __init__(self, family, kind):
        assert (family, kind) == (socket.AF_INET, socket.SOCK_DGRAM)
        self.sent: list[tuple[bytes, tuple[str, int]]] = []   # this socket's datagrams
        self.options: dict[tuple[int, int], int] = {}
        self.blocking = True
        self.closed = 0
        self.connected_to = None
        sockets.append(self)

    def setblocking(self, flag):
        self.blocking = flag

    def setsockopt(self, level, name, value):
        self.options[level, name] = value

    def connect(self, address):
        if route_from is None:
            raise OSError(errno.ENETUNREACH, 'Network is unreachable')
        self.connected_to = address

    def getsockname(self):
        return (route_from, 50000)

    def sendto(self, data, address):
        if fail_next:
            raise fail_next.pop(0)
        item = (bytes(data), address)
        self.sent.append(item)
        sent.append(item)
        return len(data)

    def close(self):
        self.closed += 1
