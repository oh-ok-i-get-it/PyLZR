import errno
import logging
import threading
import time

import pytest
from PyQt5 import sip
from PyQt5.QtCore import QObject, pyqtSignal

from fakes import udp as fake_udp
from fakes.udp import FakeSocket
from helpers import artpollreply, dmx_packets as packets, wait_until
from pylzr.core import DMX_REFRESH_HZ
from pylzr.dmx import DMXOutput, PortAddress, parse_artpollreply
from pylzr.dmx.dmx_output import ANSWER_TICKS, BLACKOUT_REPEATS, PING_TICKS, status_for

pytestmark = pytest.mark.usefixtures('qapp')     # QTimer needs a Qt application

NODE = ('10.201.6.100', 6454)
DARK = [bytes(512)] * 3
SHOW = bytes([255]) + bytes(511)


def frames() -> list[bytes]:
    return [p['data'] for p in packets()]


@pytest.fixture
def out():
    output = DMXOutput(socket_factory=FakeSocket)
    yield output
    output.close()


@pytest.fixture
def statuses(out):
    received = []
    out.status_changed.connect(lambda state, detail: received.append((state, detail)))
    return received


def test_starts_stopped_and_silent(out):
    assert not out.active
    assert (out.state, out.detail) == ('off', 'Off')
    assert out.node_ip == '10.201.6.100' and out.port == PortAddress(0, 0, 0)
    assert fake_udp.sent == []


def test_start_sends_a_frame_at_once_then_on_a_steady_timer(out, statuses):
    out.start()
    assert out.active
    assert len(packets()) == 1                   # immediately, not one interval later
    assert packets()[0]['to'] == NODE
    assert out._timer.interval() == 25           # 40 Hz
    assert statuses == [('sending', 'via 10.201.6.50')]
    wait_until(lambda: len(packets()) >= 4)      # the timer really runs


def test_each_frame_is_the_whole_universe_with_the_next_sequence(out):
    out.universe.set_range(1, [200, 37])
    out.start()
    out._tick()
    out._tick()
    assert [p['sequence'] for p in packets()] == [1, 2, 3]
    assert all(f == bytes([200, 37]) + bytes(510) for f in frames())


def test_universe_address_in_every_packet():
    out = DMXOutput(port=PortAddress(1, 2, 3), socket_factory=FakeSocket)
    out.start()
    out.close()
    assert {(p['net'], p['sub_uni']) for p in packets()} == {(1, 0x23)}


def test_blackout_is_sent_three_times():
    assert BLACKOUT_REPEATS == 3


def test_stop_sends_the_blackout_three_times_then_nothing(out, statuses):
    out.universe.set(1, 255)
    out.set_test_values(5, [255])
    out.start()
    out.stop()
    out.stop()
    assert not out.active
    assert frames()[-3:] == DARK                 # dark, even over test values
    assert len(packets()) == 1 + 3
    assert statuses[-1] == ('off', 'Off')
    assert out.universe.get(1) == 255            # the show itself is kept


def test_stopped_output_never_sends(out):
    out.set_test_values(1, [255])
    out.clear_test_values()
    out.press_note(60)
    assert fake_udp.sent == []


def test_close_blacks_out_once_and_releases_the_socket(out):
    out.start()
    out.close()
    out.close()
    assert frames()[-3:] == DARK and len(packets()) == 1 + 3
    assert fake_udp.sockets[0].closed == 1
    with pytest.raises(RuntimeError):
        out.start()
    assert not out.active                        # no timer left firing at a closed socket


def test_starting_twice_changes_nothing(out):
    out.start()
    out.start()
    assert len(packets()) == 1 and out.active


def test_test_values_go_out_over_the_show_and_clear(out):
    out.universe.set_range(1, [10, 10, 10])
    out.start()
    out.set_test_values(2, [99])
    out._tick()
    out.clear_test_values()
    out._tick()
    assert [f[:3] for f in frames()] == [bytes([10, 10, 10]), bytes([10, 99, 10]), bytes([10, 10, 10])]


def test_press_note_is_accepted_and_changes_nothing(out):
    out.start()
    out.press_note(64)
    out._tick()
    assert frames()[-1] == bytes(512)


# ── Changing node / universe ─────────────────────────────────────────────

def test_configure_while_sending_blacks_out_the_old_node(out):
    out.universe.set(1, 200)
    out.start()
    assert out.configure('10.201.6.101', PortAddress(0, 0, 1))
    old, new = [p for p in packets() if p['to'] == NODE], [p for p in packets() if p['to'] != NODE]
    assert [p['data'] for p in old[1:]] == DARK  # the old node goes dark, three times
    assert new[0]['to'] == ('10.201.6.101', 6454) and new[0]['sub_uni'] == 1
    assert new[0]['data'][0] == 200              # the new one gets the show at once
    assert fake_udp.sockets[0].closed == 1       # old socket released
    assert out.node_ip == '10.201.6.101'


def test_each_blackout_copy_has_its_own_sequence_number(out):
    """A node that drops repeated sequence numbers still takes all three."""
    out.start()
    out.stop()
    assert [p['sequence'] for p in packets()] == [1, 2, 3, 4]


def test_one_lost_blackout_send_still_leaves_two(out):
    out.start()
    fake_udp.fail_next.append(OSError(errno.ENETUNREACH, 'x'))
    out.stop()
    assert frames()[1:] == [bytes(512)] * 2


def test_configure_while_stopped_sends_nothing(out):
    assert out.configure('10.201.6.101', PortAddress())
    assert fake_udp.sent == [] and not out.active


@pytest.mark.parametrize('bad', ['10.201.6', 'node.local', ''])
def test_invalid_node_ip_is_rejected_and_nothing_changes(out, bad):
    out.start()
    assert not out.configure(bad, PortAddress(0, 0, 5))
    out._tick()
    assert out.node_ip == '10.201.6.100' and out.port == PortAddress()
    assert {p['to'] for p in packets()} == {NODE}


def test_invalid_ip_at_construction_raises():
    with pytest.raises(ValueError):
        DMXOutput('not an ip', socket_factory=FakeSocket)


# ── Emergency stop ───────────────────────────────────────────────────────
# `out` is requested before `monkeypatch`, so monkeypatch is undone before the
# fixture's close().

def test_panic_blacks_out_at_once_and_stops_on_the_next_event_pass(out, qapp):
    out.universe.set(1, 255)
    out.start()
    out.panic()
    assert len(packets()) == 1 + 3
    assert frames()[1:] == DARK
    assert out.active                             # stop() is queued, not run inside panic()
    qapp.processEvents()
    assert not out.active
    assert len(packets()) == 1 + 6
    assert frames()[-3:] == DARK
    assert out.state == 'off'
    assert out.universe.get(1) == 255             # the show is kept


def test_after_panic_only_dark_frames_go_out_until_start(out, qapp):
    out.universe.set(1, 255)
    out.start()
    out.panic()
    out._tick()
    out._tick()
    assert len(packets()) == 1 + 3                # the ticks sent nothing
    assert out.configure('10.201.6.101', PortAddress())
    assert all(f == bytes(512) for f in frames()[1:])
    assert {p['to'] for p in packets()[1:]} == {NODE}    # only the old node's blackout; the new node got nothing
    qapp.processEvents()
    assert not out.active
    out.start()
    assert frames()[-1] == SHOW


def test_frames_sent_during_a_panic_on_another_thread_are_dark(out, monkeypatch):
    out.universe.set(1, 255)
    out.start()
    real_sendto = FakeSocket.sendto
    main = threading.current_thread()

    def slow_off_main(self, data, address):
        if threading.current_thread() is not main:
            time.sleep(0.02)                      # panic() now holds the send lock for ~60 ms
        return real_sendto(self, data, address)

    monkeypatch.setattr(FakeSocket, 'sendto', slow_off_main)
    worker = threading.Thread(target=out.panic)
    worker.start()
    while worker.is_alive():
        out._tick()
        time.sleep(0.005)
    worker.join()
    sent = frames()
    first_dark = next(i for i, f in enumerate(sent) if f == bytes(512))
    assert all(f == bytes(512) for f in sent[first_dark:])


def test_panic_while_stopped_sends_nothing(out, qapp, caplog):
    with caplog.at_level(logging.DEBUG, logger='pylzr'):
        out.panic()
        qapp.processEvents()
    assert fake_udp.sent == [] and not out.active
    assert 'nothing to black out' in caplog.text
    out.start()
    assert frames() == [bytes(512)]               # the show frame: the flag was cleared


def test_panic_after_close_sends_nothing(out):
    out.start()
    out.close()
    n = len(fake_udp.sent)
    out.panic()
    assert len(fake_udp.sent) == n


def test_each_panic_copy_has_its_own_sequence_number(out):
    out.start()
    out.panic()
    assert [p['sequence'] for p in packets()] == [1, 2, 3, 4]


def test_panic_never_raises(out, monkeypatch, caplog):
    out.start()

    def raiser(data):
        raise RuntimeError('sender closed')

    with monkeypatch.context() as patched:        # undone before the fixture's close() (monkeypatch is set up first: autouse)
        patched.setattr(out._sender, 'send', raiser)
        out.panic()
    errors = [r for r in caplog.records if r.levelname == 'ERROR' and 'frame not sent' in r.getMessage()]
    assert len(errors) == 3


def test_panic_from_another_thread(out):
    out.start()
    worker = threading.Thread(target=out.panic)
    worker.start()
    worker.join()
    assert frames()[1:] == DARK
    wait_until(lambda: not out.active)            # the queued stop reached the GUI thread


def test_panic_after_the_qt_object_is_gone_still_blacks_out():
    o = DMXOutput(socket_factory=FakeSocket)
    o.start()
    sip.delete(o)
    o.panic()
    assert frames()[-3:] == DARK


# ── Status ───────────────────────────────────────────────────────────────

def test_status_is_emitted_only_on_change(out, statuses):
    out.start()
    for _ in range(3 * DMX_REFRESH_HZ):
        out._tick()
    assert statuses == [('sending', 'via 10.201.6.50')]


def test_send_errors_show_and_clear(out, statuses):
    out.start()
    fake_udp.fail_next.extend([OSError(errno.ENETUNREACH, 'x')] * 3)
    for _ in range(4):
        out._tick()
    assert statuses == [('sending', 'via 10.201.6.50'),
                        ('error', 'network unreachable'),
                        ('sending', 'via 10.201.6.50')]


def test_no_route_is_an_error(out, statuses):
    fake_udp.route_from = None
    out.start()
    assert statuses == [('error', 'no route to node')]


def test_packets_leaving_from_another_network_warn(out, statuses):
    """Cable unplugged, Wi-Fi up: the OS sends via the router and reports success."""
    fake_udp.route_from = '192.168.176.169'
    out.start()
    assert statuses == [('warning', 'via 192.168.176.169 — check cable / IP')]


def test_route_is_rechecked_every_second(out, statuses):
    fake_udp.route_from = '192.168.176.169'
    out.start()
    fake_udp.route_from = '10.201.6.50'          # cable plugged in, IP set
    for _ in range(DMX_REFRESH_HZ - 2):
        out._tick()
    assert out.state == 'warning'                # not yet: checked once a second, not per frame
    out._tick()
    out._tick()
    assert statuses[-1] == ('sending', 'via 10.201.6.50')


def test_route_check_is_not_per_frame(out):
    out.start()
    for _ in range(2 * DMX_REFRESH_HZ):
        out._tick()
    probes = [s for s in fake_udp.sockets if s.connected_to is not None]
    assert len(probes) == 3                      # at start, then once per second


def test_loopback_counts_as_the_same_network():
    fake_udp.route_from = '127.0.0.1'
    out = DMXOutput('127.0.0.1', socket_factory=FakeSocket)
    out.start()
    assert (out.state, out.detail) == ('sending', 'via 127.0.0.1')
    out.close()


# ── Status rules ─────────────────────────────────────────────────────────

@pytest.mark.parametrize('error, source, answered_by, expected', [
    (None, '10.201.6.50', None,     ('sending',   'via 10.201.6.50')),
    (None, '10.201.6.50', 'CR011R', ('connected', 'CR011R answered · via 10.201.6.50')),
    (None, '192.168.1.20', 'CR011R', ('warning',  'via 192.168.1.20 — check cable / IP')),
    (None, None,          'CR011R', ('error',     'no route to node')),
    ('host unreachable', '10.201.6.50', 'CR011R', ('error', 'host unreachable')),
])
def test_status_rules_put_problems_first(error, source, answered_by, expected):
    assert status_for(error, source, '10.201.6.100', answered_by) == expected


# ── Asking the node (with a discovery) ───────────────────────────────────

class StubDiscovery(QObject):
    """Records pings; tests emit the node's answers themselves."""

    reply_received = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.pinged: list[str] = []

    def ping(self, ip):
        self.pinged.append(ip)

    def answer(self, ip='10.201.6.100', **fields):
        self.reply_received.emit(parse_artpollreply(artpollreply(ip=ip, **fields), ip))


@pytest.fixture
def discovery():
    return StubDiscovery()


@pytest.fixture
def watched(discovery):
    output = DMXOutput(socket_factory=FakeSocket, discovery=discovery)
    yield output
    output.close()


@pytest.fixture
def watched_statuses(watched):
    received = []
    watched.status_changed.connect(lambda state, detail: received.append((state, detail)))
    return received


def ticks(output, n):
    for _ in range(n):
        output._tick()


def test_without_a_discovery_the_node_is_never_asked(out):
    out.start()
    ticks(out, 2 * PING_TICKS)
    assert len(fake_udp.sent) == len(packets()) == 1 + 2 * PING_TICKS   # DMX frames, nothing else


def test_asks_the_node_at_start_then_every_3_seconds(watched, discovery):
    assert PING_TICKS == 3 * DMX_REFRESH_HZ
    assert discovery.pinged == []                # not while stopped
    watched.start()
    assert discovery.pinged == ['10.201.6.100']
    ticks(watched, PING_TICKS - 1)
    assert len(discovery.pinged) == 1
    watched._tick()
    assert len(discovery.pinged) == 2


def test_answer_turns_the_status_connected_at_once(watched, discovery, watched_statuses):
    watched.start()
    discovery.answer()
    assert watched_statuses == [('sending', 'via 10.201.6.50'),
                                ('connected', 'CR011R answered · via 10.201.6.50')]


def test_node_without_a_name_is_shown_by_ip(watched, discovery):
    watched.start()
    discovery.answer(short_name=b'')
    assert watched.detail == '10.201.6.100 answered · via 10.201.6.50'


def test_answers_from_other_nodes_dont_count(watched, discovery):
    watched.start()
    discovery.answer(ip='10.201.6.101')
    assert watched.state == 'sending'


def test_answers_while_stopped_dont_count(watched, discovery, watched_statuses):
    discovery.answer()
    assert watched.state == 'off' and watched_statuses == []     # the indicator stays Off
    watched.start()
    assert watched.state == 'sending'


def test_regular_answers_keep_it_connected(watched, discovery, watched_statuses):
    watched.start()
    for _ in range(5):
        discovery.answer()
        ticks(watched, PING_TICKS)
    assert watched_statuses[-1][0] == 'connected' and len(watched_statuses) == 2


def test_silence_for_10_seconds_falls_back_to_sending_with_a_warning(watched, discovery, caplog):
    assert ANSWER_TICKS == 10 * DMX_REFRESH_HZ
    watched.start()
    discovery.answer()
    with caplog.at_level(logging.INFO, logger='pylzr'):
        ticks(watched, ANSWER_TICKS)
        assert watched.state == 'connected'
        watched._tick()
    assert (watched.state, watched.detail) == ('sending', 'via 10.201.6.50')
    assert [r.levelname for r in caplog.records if 'stopped answering' in r.getMessage()] == ['WARNING']


def test_answer_is_logged(watched, discovery, caplog):
    watched.start()
    with caplog.at_level(logging.INFO, logger='pylzr'):
        discovery.answer()
    assert 'CR011R at 10.201.6.100 (universe 0:0:0) answered; sending via 10.201.6.50' in caplog.text


def test_new_node_is_asked_at_once_and_old_answers_are_forgotten(watched, discovery, caplog):
    watched.start()
    discovery.answer()
    with caplog.at_level(logging.INFO, logger='pylzr'):
        watched.configure('10.201.6.101', PortAddress())
    assert discovery.pinged == ['10.201.6.100', '10.201.6.101']
    assert watched.state == 'sending'
    assert 'stopped answering' not in caplog.text   # a different node, not a silent one


def test_stop_stops_asking_and_restart_starts_fresh(watched, discovery, caplog):
    watched.start()
    discovery.answer()
    watched.stop()
    pinged = len(discovery.pinged)
    with caplog.at_level(logging.INFO, logger='pylzr'):
        watched.start()
    assert len(discovery.pinged) == pinged + 1   # asked again at once
    assert watched.state == 'sending'            # the old answer doesn't carry over
    assert 'stopped answering' not in caplog.text


def test_switching_away_and_back_is_not_a_node_going_quiet(watched, discovery, caplog):
    """The old node's answer is forgotten on any change of node, so a later
    hiccup on the same node isn't reported as it 'stopping answering'."""
    watched.start()
    discovery.answer()
    watched.configure('10.201.6.101', PortAddress())
    watched.configure('10.201.6.100', PortAddress())
    fake_udp.fail_next.append(OSError(errno.ENETUNREACH, 'x'))
    with caplog.at_level(logging.INFO, logger='pylzr'):
        ticks(watched, 2)                        # error, then sending again
    assert watched.state == 'sending'
    assert 'stopped answering' not in caplog.text


def test_a_problem_outranks_an_answer(watched, discovery):
    watched.start()
    discovery.answer()
    fake_udp.route_from = '192.168.176.169'      # cable unplugged, Wi-Fi up
    ticks(watched, DMX_REFRESH_HZ)               # next route check
    assert watched.state == 'warning'
