"""NodeDiscovery on the fake network: what it polls, which replies it
passes on, and how searches start and end."""

import errno
import logging

import pytest

from fakes import udp as fake_udp
from fakes.udp import FakeSocket
from helpers import artpollreply, wait_until
from pylzr.dmx import NodeDiscovery, PortAddress, build_artdmx, build_artpoll, is_ipv4, local_broadcasts

BROADCASTS = ['10.255.255.255', '192.168.1.255']


@pytest.fixture
def discovery(qapp):
    d = NodeDiscovery(socket_factory=FakeSocket, broadcasts=lambda: BROADCASTS)
    yield d
    d.close()


def capture(signal):
    received = []
    signal.connect(lambda *args: received.append(args[0] if len(args) == 1 else args))
    return received


def polls():
    """Where every ArtPoll went, in order."""
    return [to for data, to in fake_udp.sent if data == build_artpoll()]


# ── Opening the socket ───────────────────────────────────────────────────

def test_nothing_is_opened_until_needed(discovery):
    assert fake_udp.sockets == []


def test_listens_on_the_art_net_port(discovery):
    discovery.ping('10.201.6.100')
    [sock] = fake_udp.sockets
    assert sock.bound_to == ('', 6454)
    assert len(fake_udp.sent) == 1


def test_one_socket_however_often_it_is_used(discovery):
    discovery.ping('10.201.6.100')
    discovery.search(seconds=60)
    discovery.ping('10.201.6.100')
    assert len(fake_udp.sockets) == 1


def test_busy_port_is_used_anyway_with_a_warning(discovery, caplog):
    fake_udp.bind_fails.append(OSError(errno.EADDRINUSE, 'Address already in use'))
    with caplog.at_level(logging.WARNING, logger='pylzr'):
        discovery.ping('10.201.6.100')
    assert 'another program is using the Art-Net port' in caplog.text
    assert polls() == [('10.201.6.100', 6454)]       # still sent, to the node's port


def test_no_socket_at_all_warns_once_and_searches_find_nothing(discovery, caplog, qapp):
    fake_udp.bind_fails.extend([OSError(errno.EACCES, 'Permission denied')] * 20)   # every try
    found = capture(discovery.search_finished)
    with caplog.at_level(logging.WARNING, logger='pylzr'):
        discovery.ping('10.201.6.100')
        discovery.search(seconds=0.01)
        wait_until(lambda: found)
    assert found == [[]]
    assert fake_udp.sent == []
    assert caplog.text.count('cannot listen for Art-Net nodes') == 1


# ── Polling ──────────────────────────────────────────────────────────────

def test_search_polls_every_network_and_the_extra_targets_once_each(discovery):
    assert discovery.search(extra_targets=['10.201.6.100', '10.255.255.255'], seconds=60) is True
    assert polls() == [('10.255.255.255', 6454), ('192.168.1.255', 6454), ('10.201.6.100', 6454)]


def test_ping_polls_one_node(discovery):
    discovery.ping('10.201.6.100')
    assert polls() == [('10.201.6.100', 6454)]


def test_failed_poll_is_not_an_error(discovery):
    fake_udp.fail_next.append(OSError(errno.ENETUNREACH, 'unreachable'))
    discovery.search(seconds=60)
    assert polls() == [('192.168.1.255', 6454)]      # the first failed; the rest still go


# ── Replies ──────────────────────────────────────────────────────────────

def test_search_reports_each_reply_once_when_it_ends(discovery):
    found = capture(discovery.search_finished)
    replies = capture(discovery.reply_received)
    discovery.search(seconds=60)
    fake_udp.arrive(artpollreply(), '10.201.6.100')
    fake_udp.arrive(artpollreply(), '10.201.6.100')                   # answered twice
    fake_udp.arrive(artpollreply(ip='10.0.0.7', sw_out=(1,)), '10.0.0.7')
    discovery._drain()
    assert len(replies) == 3 and found == []         # passed on as they come; the list waits
    discovery._finish_search()
    [nodes] = found
    assert [(r.ip, r.outputs) for r in nodes] == [('10.201.6.100', (PortAddress(0, 0, 0),)),
                                                  ('10.0.0.7', (PortAddress(0, 0, 1),))]
    assert not discovery.searching


def test_one_node_answering_with_several_replies_keeps_them_all(discovery):
    found = capture(discovery.search_finished)
    discovery.search(seconds=60)
    fake_udp.arrive(artpollreply(bind_index=1), '10.201.6.100')
    fake_udp.arrive(artpollreply(bind_index=2, sw_out=(4,)), '10.201.6.100')
    discovery._finish_search()                       # also reads what just arrived
    assert [r.bind_index for r in found[0]] == [1, 2]


def test_everything_else_on_the_port_is_ignored(discovery):
    replies = capture(discovery.reply_received)
    discovery.ping('10.201.6.100')
    fake_udp.arrive(build_artpoll(), '10.201.6.50')                    # our own poll, heard back
    fake_udp.arrive(build_artdmx(bytes(512), PortAddress()), '10.201.6.9')
    fake_udp.arrive(b'\xff' * 300, '10.201.6.100')
    fake_udp.arrive(artpollreply(), '10.201.6.100')
    discovery._drain()
    assert [r.ip for r in replies] == ['10.201.6.100']


def test_ping_replies_are_passed_on_without_a_search(discovery):
    replies = capture(discovery.reply_received)
    found = capture(discovery.search_finished)
    discovery.ping('10.201.6.100')
    fake_udp.arrive(artpollreply(), '10.201.6.100')
    wait_until(lambda: replies)                      # read by the 50 ms timer
    assert replies[0].short_name == 'CR011R'
    assert found == [] and not discovery.searching


def test_search_ends_by_itself(discovery):
    found = capture(discovery.search_finished)
    discovery.search(seconds=0.05)
    assert discovery.searching
    fake_udp.arrive(artpollreply(), '10.201.6.100')
    wait_until(lambda: found)
    assert [r.ip for r in found[0]] == ['10.201.6.100']


# ── One search at a time ─────────────────────────────────────────────────

def test_second_search_while_searching_is_ignored(discovery):
    found = capture(discovery.search_finished)
    discovery.search(seconds=60)
    sent = len(fake_udp.sent)
    assert discovery.search(seconds=60) is False
    assert len(fake_udp.sent) == sent
    discovery._finish_search()
    assert len(found) == 1


def test_each_search_starts_empty(discovery):
    found = capture(discovery.search_finished)
    discovery.search(seconds=60)
    fake_udp.arrive(artpollreply(), '10.201.6.100')
    discovery._finish_search()
    discovery.search(seconds=60)
    discovery._finish_search()
    assert [len(nodes) for nodes in found] == [1, 0]


# ── Closing ──────────────────────────────────────────────────────────────

def test_close_ends_everything_quietly(discovery, qapp):
    found = capture(discovery.search_finished)
    discovery.search(seconds=0.01)
    discovery.close()
    discovery.close()
    assert fake_udp.sockets[0].closed == 1
    assert not discovery.searching
    assert not discovery._drain_timer.isActive() and not discovery._search_timer.isActive()
    with pytest.raises(RuntimeError):
        discovery.ping('10.201.6.100')
    with pytest.raises(RuntimeError):
        discovery.search()
    assert found == []


def test_close_before_use_opens_nothing_ever(discovery):
    discovery.close()
    with pytest.raises(RuntimeError):
        discovery.ping('10.201.6.100')
    with pytest.raises(RuntimeError):
        discovery.search()
    assert fake_udp.sockets == []


# ── This computer's networks ─────────────────────────────────────────────

def test_local_broadcasts_are_ipv4_and_never_loopback(qapp):
    addresses = local_broadcasts()
    assert all(is_ipv4(a) and not a.startswith('127.') for a in addresses)
    assert len(addresses) == len(set(addresses))
