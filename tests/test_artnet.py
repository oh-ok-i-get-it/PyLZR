import pytest

from pylzr.dmx import ARTNET_PORT, PortAddress, build_artdmx, next_sequence


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
