import errno
import socket

import pytest

from fakes import udp as fake_udp
from fakes.udp import FakeSocket
from pylzr.dmx import UdpSender


@pytest.fixture
def sender():
    return UdpSender('10.201.6.100', 6454, socket_factory=FakeSocket)


def test_socket_setup(sender):
    sock = fake_udp.sockets[0]
    assert sock.blocking is False                                  # never stalls the GUI thread
    assert sock.options[socket.SOL_SOCKET, socket.SO_BROADCAST] == 1


def test_send(sender):
    assert sender.send(b'abc') is True
    assert fake_udp.sent == [(b'abc', ('10.201.6.100', 6454))]
    assert sender.last_error is None


@pytest.mark.parametrize('host', ['10.201.6', '10.201.6.256', 'node.local', '::1', ''])
def test_host_must_be_dotted_ipv4(host):
    with pytest.raises(ValueError):
        UdpSender(host, 6454, socket_factory=FakeSocket)


@pytest.mark.parametrize('port', [0, 65536])
def test_port_range(port):
    with pytest.raises(ValueError):
        UdpSender('127.0.0.1', port, socket_factory=FakeSocket)


@pytest.mark.parametrize('code, text', [
    (errno.ENETUNREACH,   'network unreachable'),   # 10051 on Windows, 51/101 on macOS/Linux
    (errno.EHOSTUNREACH,  'host unreachable'),
    (errno.ENETDOWN,      'network is down'),
    (errno.EADDRNOTAVAIL, 'address not available'),
])
def test_network_errors_are_reported_not_raised(sender, code, text):
    fake_udp.fail_next.append(OSError(code, 'raw OS message'))
    assert sender.send(b'x') is False
    assert sender.last_error == text
    assert sender.send(b'x') is True             # cable plugged back in
    assert sender.last_error is None


def test_unknown_errors_use_the_os_message(sender):
    fake_udp.fail_next.append(OSError(errno.EPERM, 'Operation not permitted'))
    assert sender.send(b'x') is False
    assert sender.last_error == 'Operation not permitted'


def test_full_send_buffer_drops_one_datagram(sender):
    fake_udp.fail_next.append(BlockingIOError(errno.EWOULDBLOCK, 'would block'))
    assert sender.send(b'x') is False
    assert sender.dropped == 1
    assert sender.last_error is None             # not an error state
    assert sender.send(b'y') is True


def test_close_is_idempotent_and_final(sender):
    sender.close()
    sender.close()
    assert fake_udp.sockets[0].closed == 1
    with pytest.raises(RuntimeError):
        sender.send(b'x')


def test_source_address_sends_nothing_and_closes_its_probe(sender):
    assert sender.source_address() == '10.201.6.50'
    probe = fake_udp.sockets[1]                  # [0] is the sending socket
    assert probe.connected_to == ('10.201.6.100', 6454)
    assert probe.closed == 1
    assert fake_udp.sent == []


def test_source_address_without_a_route(sender):
    fake_udp.route_from = None
    assert sender.source_address() is None
    assert fake_udp.sockets[1].closed == 1


def test_real_source_address_for_loopback():
    sender = UdpSender('127.0.0.1', 6454)
    try:
        assert sender.source_address() == '127.0.0.1'
    finally:
        sender.close()


def test_real_datagram_over_loopback():
    """End to end through the operating system's network stack (127.0.0.1 only)."""
    receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    receiver.bind(('127.0.0.1', 0))
    receiver.settimeout(5)
    sender = UdpSender('127.0.0.1', receiver.getsockname()[1])
    try:
        assert sender.send(b'Art-Net\x00 hello')
        data, (source_ip, _) = receiver.recvfrom(1024)
        assert data == b'Art-Net\x00 hello'
        assert source_ip == '127.0.0.1'
    finally:
        sender.close()
        receiver.close()
