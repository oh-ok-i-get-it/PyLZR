import errno
import socket
import time

import pytest

from fakes import udp as fake_udp
from fakes.udp import FakeSocket
from pylzr.dmx import UdpListener


@pytest.fixture
def listener():
    return UdpListener(6454, socket_factory=FakeSocket)


# ── Binding ──────────────────────────────────────────────────────────────

def test_socket_setup(listener):
    sock = fake_udp.sockets[0]
    assert sock.bound_to == ('', 6454)                             # every network
    assert sock.options[socket.SOL_SOCKET, socket.SO_REUSEADDR] == 1   # shares the port
    assert sock.options[socket.SOL_SOCKET, socket.SO_BROADCAST] == 1
    assert sock.blocking is False                                  # never stalls the GUI thread
    assert (listener.port, listener.fallback) == (6454, False)


@pytest.mark.parametrize('platform, shares', [('darwin', True), ('linux', False), ('win32', False)])
def test_macos_also_needs_reuse_port(monkeypatch, platform, shares):
    """Linux's SO_REUSEPORT would split unicast replies between programs,
    and Windows has none, so it's set on macOS only."""
    monkeypatch.setattr('sys.platform', platform)
    monkeypatch.setattr(socket, 'SO_REUSEPORT', 0x0200, raising=False)
    UdpListener(6454, socket_factory=FakeSocket)
    assert ((socket.SOL_SOCKET, 0x0200) in fake_udp.sockets[0].options) is shares


def test_taken_port_falls_back_to_any_free_port():
    fake_udp.bind_fails.append(OSError(errno.EADDRINUSE, 'Address already in use'))
    listener = UdpListener(6454, socket_factory=FakeSocket)
    first, second = fake_udp.sockets
    assert first.closed == 1
    assert second.bound_to == ('', 0)
    assert (listener.port, listener.fallback) == (fake_udp.ANY_FREE_PORT, True)


def test_no_port_at_all_raises_and_leaks_no_socket():
    fake_udp.bind_fails.extend([OSError(errno.EACCES, 'denied')] * 2)
    with pytest.raises(OSError):
        UdpListener(6454, socket_factory=FakeSocket)
    assert [sock.closed for sock in fake_udp.sockets] == [1, 1]


def test_port_zero_asks_for_any_port_without_fallback():
    listener = UdpListener(0, bind_host='127.0.0.1', socket_factory=FakeSocket)
    assert fake_udp.sockets[0].bound_to == ('127.0.0.1', 0)
    assert listener.fallback is False
    fake_udp.reset()
    fake_udp.bind_fails.append(OSError(errno.EACCES, 'denied'))
    with pytest.raises(OSError):
        UdpListener(0, socket_factory=FakeSocket)
    assert len(fake_udp.sockets) == 1                              # no second try


@pytest.mark.parametrize('port', [-1, 65536])
def test_port_range(port):
    with pytest.raises(ValueError):
        UdpListener(port, socket_factory=FakeSocket)


# ── Sending ──────────────────────────────────────────────────────────────

def test_send_to_any_host(listener):
    assert listener.send(b'poll', '10.255.255.255', 6454) is True
    assert listener.send(b'poll', '10.201.6.100', 6454) is True
    assert fake_udp.sent == [(b'poll', ('10.255.255.255', 6454)), (b'poll', ('10.201.6.100', 6454))]


def test_send_errors_are_reported_not_raised(listener):
    fake_udp.fail_next.append(OSError(errno.ENETUNREACH, 'raw OS message'))
    assert listener.send(b'x', '10.201.6.100', 6454) is False
    assert listener.last_error == 'network unreachable'
    assert listener.send(b'x', '10.201.6.100', 6454) is True
    assert listener.last_error is None


@pytest.mark.parametrize('host, port', [('node.local', 6454), ('10.201.6', 6454), ('10.201.6.100', 0)])
def test_send_needs_an_ipv4_address_and_port(listener, host, port):
    with pytest.raises(ValueError):
        listener.send(b'x', host, port)


# ── Receiving ────────────────────────────────────────────────────────────

def test_receive_returns_waiting_datagrams_oldest_first(listener):
    assert listener.receive() == []                                # nothing waiting
    fake_udp.arrive(b'one', '10.201.6.100')
    fake_udp.arrive(b'two', '10.201.6.101', port=50123)
    assert listener.receive() == [(b'one', '10.201.6.100'), (b'two', '10.201.6.101')]
    assert listener.receive() == []


def test_receive_takes_at_most_limit_per_call(listener):
    for i in range(5):
        fake_udp.arrive(bytes([i]), '10.201.6.100')
    assert [data for data, _ in listener.receive(limit=2)] == [b'\x00', b'\x01']
    assert [data for data, _ in listener.receive(limit=10)] == [b'\x02', b'\x03', b'\x04']


def test_receive_skips_windows_connection_resets(listener):
    fake_udp.incoming.append(ConnectionResetError(errno.ECONNRESET, 'reset'))
    fake_udp.arrive(b'reply', '10.201.6.100')
    assert listener.receive() == [(b'reply', '10.201.6.100')]


def test_receive_stops_at_other_errors_without_raising(listener):
    fake_udp.incoming.append(OSError(errno.ENETDOWN, 'raw OS message'))
    fake_udp.arrive(b'later', '10.201.6.100')
    assert listener.receive() == []
    assert listener.last_error == 'network is down'
    assert listener.receive() == [(b'later', '10.201.6.100')]   # tried again next time


def test_close_is_idempotent_and_final(listener):
    listener.close()
    listener.close()
    assert fake_udp.sockets[0].closed == 1
    with pytest.raises(RuntimeError):
        listener.send(b'x', '10.201.6.100', 6454)
    with pytest.raises(RuntimeError):
        listener.receive()


# ── Through the real network stack (127.0.0.1 only) ──────────────────────

def test_real_round_trip_over_loopback():
    """Both directions through the operating system: a 'node' socket sends a
    datagram to the listener, and the listener answers it."""
    listener = UdpListener(0, bind_host='127.0.0.1')
    node = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    node.bind(('127.0.0.1', 0))
    node.settimeout(5)
    try:
        assert listener.port != 0
        node.sendto(b'Art-Net\x00 reply', ('127.0.0.1', listener.port))
        deadline = time.monotonic() + 5
        received = []
        while not received and time.monotonic() < deadline:
            received = listener.receive()
            time.sleep(0.005)
        assert received == [(b'Art-Net\x00 reply', '127.0.0.1')]

        assert listener.send(b'Art-Net\x00 poll', '127.0.0.1', node.getsockname()[1])
        data, (source_ip, source_port) = node.recvfrom(1024)
        assert (data, source_ip, source_port) == (b'Art-Net\x00 poll', '127.0.0.1', listener.port)
    finally:
        listener.close()
        node.close()
