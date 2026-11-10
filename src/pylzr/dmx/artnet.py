"""Art-Net 4 packet encoding. Pure functions: no sockets, no Qt.

Only what PyLZR uses is implemented: it sends ArtDmx (one universe of DMX
data) and ArtPoll ("which nodes are there?"), and reads ArtPollReply (a
node's answer: its name, IP and DMX outputs).
Spec: https://art-net.org.uk (Art-Net 4, "ArtDmx", "ArtPoll", "ArtPollReply").
"""

import ipaddress
import struct
from dataclasses import dataclass

ARTNET_PORT = 6454            # UDP port every Art-Net node listens on

_ID            = b'Art-Net\x00'
_OP_POLL       = 0x2000       # OpCodes, sent little-endian
_OP_POLL_REPLY = 0x2100
_OP_DMX        = 0x5000
_PROTOCOL_VER  = 14           # sent big-endian
_HEADER        = struct.Struct('<8sH')       # ID, OpCode
_POLL_FIELDS   = struct.Struct('>HBB')       # ProtVer, Flags, DiagPriority
_DMX_FIELDS    = struct.Struct('>HBBBBH')    # ProtVer, Sequence, Physical, SubUni, Net, Length

# ArtPollReply field offsets. A reply has no ProtVer: the node's IP follows
# the OpCode. Replies shorter than _REPLY_MIN are invalid; fields past the
# end of a valid but short reply read as 0, as the spec says.
_REPLY_MIN    = 207
_R_IP         = slice(10, 14)
_R_NET        = 18            # NetSwitch: Net in bits 0–6
_R_SUBNET     = 19            # SubSwitch: SubNet in bits 0–3
_R_SHORT_NAME = slice(26, 44)
_R_LONG_NAME  = slice(44, 108)
_R_REPORT     = slice(108, 172)
_R_NUM_PORTS  = 173           # NumPortsLo (NumPortsHi is reserved)
_R_PORT_TYPES = 174           # 4 bytes, one per port; bit 7 = outputs DMX
_R_SW_OUT     = 190           # 4 bytes: each port's Universe in bits 0–3
_R_MAC        = slice(201, 207)
_R_BIND_INDEX = 211
_MAX_PORTS    = 4             # per reply; bigger nodes send one reply per 4 ports
_PORT_OUTPUTS = 0x80

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


def build_artpoll() -> bytes:
    """An ArtPoll: asks every node that receives it to answer with an
    ArtPollReply. This is the classic 14-byte form, which every Art-Net
    version accepts. Flags 0: reply once, no diagnostics."""
    return _HEADER.pack(_ID, _OP_POLL) + _POLL_FIELDS.pack(_PROTOCOL_VER, 0, 0)


@dataclass(frozen=True)
class PollReply:
    """What a node says about itself in an ArtPollReply."""

    ip:         str                       # where to send its DMX
    short_name: str                       # e.g. 'CR011R'
    long_name:  str
    report:     str                       # the node's status text, e.g. '#0001 [0042] Power On Tests successful'
    mac:        str | None                # 'aa:bb:cc:dd:ee:ff', or None if not given
    bind_index: int                       # which of a big node's replies this is (0 or 1 = the first)
    outputs:    tuple[PortAddress, ...]   # universes it outputs as DMX; empty if none


def parse_artpollreply(data: bytes, sender_ip: str) -> PollReply | None:
    """The PollReply in `data`, or None if `data` isn't a valid ArtPollReply.
    Network data is untrusted: anything malformed is rejected, never raised.
    sender_ip (the datagram's source) is used if the reply's IP field is
    0.0.0.0."""
    if len(data) < _REPLY_MIN or _HEADER.unpack_from(data) != (_ID, _OP_POLL_REPLY):
        return None
    data = bytes(data).ljust(_R_BIND_INDEX + 1, b'\x00')
    ip = str(ipaddress.IPv4Address(data[_R_IP]))
    net, subnet = data[_R_NET] & 0x7F, data[_R_SUBNET] & 0x0F
    ports = range(min(data[_R_NUM_PORTS], _MAX_PORTS))
    mac = data[_R_MAC]
    return PollReply(
        ip=sender_ip if ip == '0.0.0.0' else ip,
        short_name=_text(data[_R_SHORT_NAME]),
        long_name=_text(data[_R_LONG_NAME]),
        report=_text(data[_R_REPORT]),
        mac=':'.join(f'{b:02x}' for b in mac) if any(mac) else None,
        bind_index=data[_R_BIND_INDEX],
        outputs=tuple(PortAddress(net, subnet, data[_R_SW_OUT + i] & 0x0F)
                      for i in ports if data[_R_PORT_TYPES + i] & _PORT_OUTPUTS),
    )


def _text(field: bytes) -> str:
    """A NUL-terminated ASCII field as safe display text: anything after the
    NUL, non-ASCII bytes and control characters are dropped."""
    text = field.split(b'\x00', 1)[0].decode('ascii', errors='ignore')
    return ''.join(ch for ch in text if ch.isprintable()).strip()
