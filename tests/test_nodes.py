import pytest

from helpers import artpollreply
from pylzr.dmx import NodeChoice, NodeWatch, PortAddress, node_choices, parse_artpollreply


def reply(ip='10.201.6.100', **fields):
    return parse_artpollreply(artpollreply(ip=ip, **fields), ip)


def labels(choices):
    return [choice.label for choice in choices]


# ── node_choices ─────────────────────────────────────────────────────────

def test_one_choice_per_output():
    choices = node_choices([reply(net=1, subnet=2, port_types=(0x80, 0x80), sw_out=(3, 4))])
    assert choices == [
        NodeChoice('CR011R · 10.201.6.100 · 1:2:3', '10.201.6.100', PortAddress(1, 2, 3),
                   'Art-Net node\n#0001 [0001] Power On Tests successful\nMAC 00:1a:2b:3c:4d:5e'),
        NodeChoice('CR011R · 10.201.6.100 · 1:2:4', '10.201.6.100', PortAddress(1, 2, 4),
                   'Art-Net node\n#0001 [0001] Power On Tests successful\nMAC 00:1a:2b:3c:4d:5e'),
    ]
    assert all(choice.enabled for choice in choices)


@pytest.mark.parametrize('short, long, shown', [
    (b'CR011R', b'Pknight node', 'CR011R'),
    (b'', b'Pknight node', 'Pknight node'),
    (b'', b'', 'Art-Net node'),
])
def test_name_falls_back_to_the_long_name_then_a_generic_one(short, long, shown):
    [choice] = node_choices([reply(short_name=short, long_name=long)])
    assert choice.label == f'{shown} · 10.201.6.100 · 0:0:0'


def test_tooltip_leaves_out_blank_lines():
    [choice] = node_choices([reply(long_name=b'', report=b'', mac=bytes(6))])
    assert choice.tooltip == ''
    [choice] = node_choices([reply(long_name=b'', mac=bytes(6))])
    assert choice.tooltip == '#0001 [0001] Power On Tests successful'


def test_node_without_outputs_gets_one_entry_that_cant_be_chosen():
    """E.g. a CR011R left on DMX → Art-Net."""
    [choice] = node_choices([reply(port_types=(0x40,))])
    assert choice.label == 'CR011R · 10.201.6.100 — no DMX outputs (set it to Art-Net → DMX)'
    assert (choice.ip, choice.port, choice.enabled) == ('10.201.6.100', None, False)


def test_replies_from_one_node_are_combined():
    """A big node answers once per group of 4 ports; the same port twice
    (e.g. the reply to two polls) is listed once."""
    first  = reply(port_types=(0x80, 0x80), sw_out=(0, 1), bind_index=1)
    second = reply(short_name=b'other name', port_types=(0x80,), sw_out=(2,), bind_index=2)
    choices = node_choices([second, first, first])
    assert labels(choices) == ['CR011R · 10.201.6.100 · 0:0:0', 'CR011R · 10.201.6.100 · 0:0:1',
                               'CR011R · 10.201.6.100 · 0:0:2']                 # named by its first reply


def test_outputs_in_one_reply_cancel_the_no_outputs_entry():
    choices = node_choices([reply(port_types=(0x40,), bind_index=1),
                            reply(port_types=(0x80,), sw_out=(5,), bind_index=2)])
    assert labels(choices) == ['CR011R · 10.201.6.100 · 0:0:5']


def test_ordered_by_ip_as_numbers_then_universe():
    choices = node_choices([
        reply('10.0.0.10'),
        reply('10.0.0.9', net=1, port_types=(0x80, 0x80), sw_out=(1, 0)),
        reply('9.255.0.1', port_types=(0x40,)),
    ])
    assert [(c.ip, str(c.port)) for c in choices] == [
        ('9.255.0.1', 'None'), ('10.0.0.9', '1:0:0'), ('10.0.0.9', '1:0:1'), ('10.0.0.10', '0:0:0')]


def test_universes_sort_by_port_address_not_text():
    """0:0:9 before 0:0:10, and 1:0:0 (port address 256) after 0:15:15 (255)."""
    choices = node_choices([reply(port_types=(0x80, 0x80), sw_out=(10, 9), bind_index=1),
                            reply(port_types=(0x80,), sw_out=(0,), net=1, bind_index=2),
                            reply(port_types=(0x80,), sw_out=(15,), subnet=15, bind_index=3)])
    assert [str(c.port) for c in choices] == ['0:0:9', '0:0:10', '0:15:15', '1:0:0']


def test_no_replies_no_choices():
    assert node_choices([]) == []


# ── NodeWatch ────────────────────────────────────────────────────────────

def due_ticks(watch, ticks):
    """Which of the next `ticks` ticks (1-based) say a ping is due."""
    return [t for t in range(1, ticks + 1) if watch.tick()]


def test_ping_on_the_first_tick_then_every_ping_every_ticks():
    assert due_ticks(NodeWatch(3, 10), 10) == [1, 4, 7, 10]
    assert due_ticks(NodeWatch(1, 1), 3) == [1, 2, 3]


def test_restart_pings_on_the_next_tick():
    watch = NodeWatch(3, 10)
    due_ticks(watch, 2)                          # ticks 1 (due) and 2
    watch.restart()
    assert due_ticks(watch, 4) == [1, 4]         # straight away, then every 3


def test_answer_lasts_exactly_answer_within_ticks():
    watch = NodeWatch(3, 10)
    watch.tick()
    watch.heard('CR011R')
    assert watch.answered_by == 'CR011R'
    for _ in range(10):
        watch.tick()
    assert watch.answered_by == 'CR011R'         # 10 ticks old: still counts
    watch.tick()
    assert watch.answered_by is None             # 11: too old


def test_a_new_answer_renews_it():
    watch = NodeWatch(3, 10)
    watch.heard('CR011R')
    for _ in range(8):
        watch.tick()
    watch.heard('CR011R (renamed)')
    for _ in range(10):
        watch.tick()
    assert watch.answered_by == 'CR011R (renamed)'


def test_no_answer_yet():
    watch = NodeWatch(3, 10)
    assert watch.answered_by is None
    due_ticks(watch, 20)
    assert watch.answered_by is None


def test_answer_before_the_first_tick_counts():
    watch = NodeWatch(3, 10)
    watch.heard('CR011R')
    assert watch.answered_by == 'CR011R'


def test_restart_forgets_the_answer():
    watch = NodeWatch(3, 10)
    watch.heard('CR011R')
    watch.restart()
    assert watch.answered_by is None


@pytest.mark.parametrize('ping_every, answer_within', [(0, 10), (11, 10), (-1, -1)])
def test_invalid_timing(ping_every, answer_within):
    with pytest.raises(ValueError):
        NodeWatch(ping_every, answer_within)
