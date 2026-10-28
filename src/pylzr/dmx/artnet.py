"""Art-Net 4 packet encoding. Pure functions: no sockets, no Qt.

Only what PyLZR sends is implemented: ArtDmx, one universe of DMX data.
Spec: https://art-net.org.uk (Art-Net 4, "ArtDmx").
"""

import struct
from dataclasses import dataclass

ARTNET_PORT = 6454            # UDP port every Art-Net node listens on

_ID           = b'Art-Net\x00'
_OP_DMX       = 0x5000        # OpCode, sent little-endian
_PROTOCOL_VER = 14            # sent big-endian
_HEADER       = struct.Struct('<8sH')       # ID, OpCode
_DMX_FIELDS   = struct.Struct('>HBBBBH')    # ProtVer, Sequence, Physical, SubUni, Net, Length

MAX_SEQUENCE = 255            # 1–255 cycle; 0 means "sequencing off"
MAX_DATA     = 512


@dataclass(frozen=True)
class PortAddress:
    """Which universe a packet is for, as the node's own menu shows it:
    Net (0–127) · SubNet (0–15) · Universe (0–15). Together these form the
    15-bit Art-Net port address."""

    net:      int = 0
    subnet:   int = 0
    universe: int = 0

    def __post_init__(self):
        for name, value, top in (('net', self.net, 127), ('subnet', self.subnet, 15),
                                 ('universe', self.universe, 15)):
            if not (isinstance(value, int) and 0 <= value <= top):
                raise ValueError(f'{name} must be an int 0–{top}, got {value!r}')

    @property
    def value(self) -> int:
        """The 15-bit port address."""
        return self.net << 8 | self.subnet << 4 | self.universe

    @property
    def sub_uni(self) -> int:
        """Low byte of the port address (SubNet in the high nibble)."""
        return self.subnet << 4 | self.universe

    def __str__(self) -> str:
        return f'{self.net}:{self.subnet}:{self.universe}'


def next_sequence(sequence: int) -> int:
    """The sequence number after `sequence`: 1, 2, … 255, 1, … (never 0)."""
    return sequence % MAX_SEQUENCE + 1


def build_artdmx(data: bytes, port: PortAddress, sequence: int = 0, physical: int = 0) -> bytes:
    """An ArtDmx packet carrying `data` (2–512 channel values, channel 1
    first) to `port`. Odd lengths are padded with one zero, as the spec
    requires an even length. sequence: 1–255 lets the node reorder late
    packets; 0 disables that."""
    length = len(data)
    if not 2 <= length <= MAX_DATA:
        raise ValueError(f'ArtDmx carries 2–{MAX_DATA} channels, got {length}')
    if not 0 <= sequence <= MAX_SEQUENCE:
        raise ValueError(f'sequence must be 0–{MAX_SEQUENCE}, got {sequence}')
    if not 0 <= physical <= 255:
        raise ValueError(f'physical must be 0–255, got {physical}')
    if length % 2:
        data, length = bytes(data) + b'\x00', length + 1
    return (_HEADER.pack(_ID, _OP_DMX)
            + _DMX_FIELDS.pack(_PROTOCOL_VER, sequence, physical, port.sub_uni, port.net, length)
            + bytes(data))
