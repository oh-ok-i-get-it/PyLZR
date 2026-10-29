import pytest

from helpers import artpollreply
from pylzr.dmx import (ARTNET_PORT, PollReply, PortAddress, build_artdmx, build_artpoll, next_sequence,
                       parse_artpollreply)


def test_artdmx_bytes_match_the_spec():
    """Every header field, written out by hand from the Art-Net 4 ArtDmx table."""
    packet = build_artdmx(bytes([10, 20, 30, 40]), PortAddress(net=1, subnet=2, universe=3),
                          sequence=7, physical=1)
    assert packet == bytes([
        *b'Art-Net', 0x00,     # ID
        0x00, 0x50,            # OpCode 0x5000, low byte first
        0x00, 14,              # ProtVerHi, ProtVerLo
        7,                     # Sequence
        1,                     # Physical
        0x23,                  # SubUni: SubNet 2 (high nibble), Universe 3
        1,                     # Net
        0x00, 0x04,            # Length, high byte first
        10, 20, 30, 40,        # data
    ])


def test_full_universe():
    packet = build_artdmx(bytes(range(256)) * 2, PortAddress())
    assert len(packet) == 18 + 512
    assert packet[16:18] == b'\x02\x00'          # 512, big-endian
    assert packet[18:] == bytes(range(256)) * 2


def test_odd_length_is_padded_to_even():
    packet = build_artdmx(b'\x01\x02\x03', PortAddress())
    assert packet[16:18] == b'\x00\x04'
    assert packet[18:] == b'\x01\x02\x03\x00'


@pytest.mark.parametrize('length', [0, 1, 513])
def test_data_length_limits(length):
    with pytest.raises(ValueError):
        build_artdmx(bytes(length), PortAddress())


@pytest.mark.parametrize('kwargs', [{'sequence': -1}, {'sequence': 256}, {'physical': 256}])
def test_header_field_limits(kwargs):
    with pytest.raises(ValueError):
        build_artdmx(bytes(2), PortAddress(), **kwargs)


def test_port_address_encoding():
    port = PortAddress(net=127, subnet=15, universe=15)
    assert port.value == 0x7FFF                  # the largest 15-bit port address
    assert port.sub_uni == 0xFF
    assert PortAddress(net=1, subnet=0, universe=0).value == 256
    assert PortAddress(net=0, subnet=1, universe=0).value == 16
    assert PortAddress().value == 0
    assert str(PortAddress(1, 2, 3)) == '1:2:3'


@pytest.mark.parametrize('kwargs', [
    {'net': 128}, {'subnet': 16}, {'universe': 16}, {'net': -1}, {'universe': 1.0},
])
def test_port_address_limits(kwargs):
    with pytest.raises(ValueError):
        PortAddress(**kwargs)


def test_sequence_cycles_through_1_to_255_never_0():
    assert next_sequence(0) == 1                 # first packet after "off"
    assert next_sequence(1) == 2
    assert next_sequence(254) == 255
    assert next_sequence(255) == 1


def test_art_net_port():
    assert ARTNET_PORT == 6454


# ── ArtPoll / ArtPollReply ───────────────────────────────────────────────

def test_artpoll_bytes_match_the_spec():
    assert build_artpoll() == bytes([
        *b'Art-Net', 0x00,     # ID
        0x00, 0x20,            # OpCode 0x2000, low byte first
        0x00, 14,              # ProtVerHi, ProtVerLo
        0x00,                  # Flags: reply once, no diagnostics
        0x00,                  # DiagPriority
    ])


def test_reply_fields():
    reply = parse_artpollreply(artpollreply(), '10.201.6.100')
    assert reply == PollReply(ip='10.201.6.100', short_name='CR011R', long_name='Art-Net node',
                              report='#0001 [0001] Power On Tests successful', mac='00:1a:2b:3c:4d:5e',
                              bind_index=1, outputs=(PortAddress(0, 0, 0),))


def test_reply_outputs_combine_net_subnet_and_each_ports_universe():
    """Ports 1 and 3 output DMX, port 2 only inputs it. Bits outside each
    field (Net bit 7, high nibbles) are ignored."""
    data = artpollreply(net=0x83, subnet=0xF2, port_types=(0x80, 0x40, 0xC0), sw_out=(0x01, 0x02, 0x1F))
    assert parse_artpollreply(data, '10.201.6.100').outputs == (PortAddress(3, 2, 1), PortAddress(3, 2, 15))


@pytest.mark.parametrize('num_ports, expected', [(0, 0), (2, 2), (4, 4), (9, 4)])
def test_reply_reads_only_the_ports_it_reports(num_ports, expected):
    """At most 4 ports per reply: the bytes after PortTypes (GoodInput, set
    to look like output ports here) are never read as ports."""
    data = bytearray(artpollreply(port_types=(0x80,) * 4, sw_out=(0, 1, 2, 3), num_ports=num_ports))
    data[178:182] = b'\x80' * 4
    outputs = parse_artpollreply(data, '10.201.6.100').outputs
    assert outputs == tuple(PortAddress(0, 0, u) for u in range(expected))


def test_node_that_only_inputs_dmx_has_no_outputs():
    """E.g. a CR011R set to DMX → Art-Net."""
    data = artpollreply(port_types=(0x40,))
    assert parse_artpollreply(data, '10.201.6.100').outputs == ()


def test_reply_without_its_own_ip_uses_the_sender():
    reply = parse_artpollreply(artpollreply(ip='0.0.0.0'), '10.201.6.100')
    assert reply.ip == '10.201.6.100'


def test_reply_ip_wins_over_the_sender():
    """The IP field is where the node takes DMX, even if the reply came from
    another address."""
    reply = parse_artpollreply(artpollreply(ip='10.201.6.100'), '10.201.6.7')
    assert reply.ip == '10.201.6.100'


@pytest.mark.parametrize('raw, shown', [
    (b'CR011R\x00junk after the end', 'CR011R'),
    (b'ABCDEFGHIJKLMNOPQR', 'ABCDEFGHIJKLMNOPQR'),       # all 18 bytes, no terminating NUL
    (b' Caf\xe9\x07 node\n', 'Caf node'),                 # non-ASCII and control characters dropped
    (b'', ''),
])
def test_names_are_cleaned_for_display(raw, shown):
    assert parse_artpollreply(artpollreply(short_name=raw), '10.201.6.100').short_name == shown


def test_missing_mac_is_none():
    assert parse_artpollreply(artpollreply(mac=bytes(6)), '10.201.6.100').mac is None


def test_shortest_valid_reply_reads_missing_fields_as_zero():
    """207 bytes (up to the MAC) is the spec's minimum; BindIndex is past it."""
    reply = parse_artpollreply(artpollreply(bind_index=5)[:207], '10.201.6.100')
    assert reply.mac == '00:1a:2b:3c:4d:5e'
    assert reply.bind_index == 0


@pytest.mark.parametrize('data', [
    artpollreply()[:206],                                 # too short
    b'Art-Net\x00' + artpollreply()[8:].replace(b'\x00\x21', b'\x00\x20', 1),   # an ArtPoll's OpCode
    b'Art-Nyt\x00' + artpollreply()[8:],                  # wrong ID
    build_artpoll(),                                      # our own poll, heard back
    build_artdmx(bytes(512), PortAddress()),              # DMX data: long enough, wrong OpCode
    b'',
    bytes(range(256)),
], ids=['short', 'opcode', 'id', 'artpoll', 'artdmx', 'empty', 'garbage'])
def test_anything_else_is_not_a_reply(data):
    assert parse_artpollreply(data, '10.201.6.100') is None
