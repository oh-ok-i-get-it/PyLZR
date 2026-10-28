import errno

import pytest

from fakes import udp as fake_udp
from fakes.udp import FakeSocket
from helpers import wait_until
from pylzr.core import DMX_REFRESH_HZ
from pylzr.dmx import DMXOutput, PortAddress

pytestmark = pytest.mark.usefixtures('qapp')     # QTimer needs a Qt application

NODE = ('10.201.6.100', 6454)


def packets() -> list[dict]:
    """Every ArtDmx packet sent so far, decoded."""
    return [{'to': to, 'sequence': p[12], 'sub_uni': p[14], 'net': p[15], 'data': p[18:]}
            for p, to in fake_udp.sent]


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


def test_stop_sends_one_blackout_then_nothing(out, statuses):
    out.universe.set(1, 255)
    out.set_test_values(5, [255])
    out.start()
    out.stop()
    out.stop()
    assert not out.active
    assert frames()[-1] == bytes(512)            # dark, even over test values
    assert len(packets()) == 2
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
    assert frames()[-1] == bytes(512) and len(packets()) == 2
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
    assert old[-1]['data'] == bytes(512)         # the old node goes dark
    assert new[0]['to'] == ('10.201.6.101', 6454) and new[0]['sub_uni'] == 1
    assert new[0]['data'][0] == 200              # the new one gets the show at once
    assert fake_udp.sockets[0].closed == 1       # old socket released
    assert out.node_ip == '10.201.6.101'


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
