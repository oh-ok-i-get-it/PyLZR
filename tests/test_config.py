import ipaddress

from pylzr import core
from pylzr.core import CONTROL_MODES, DMX_CHANNELS, DMX_DEFAULT_NODE_IP, DMX_REFRESH_HZ


def test_every_config_constant_is_exported():
    assert set(core.config.__all__) == {name for name in vars(core.config) if name.isupper()}


def test_control_modes_start_with_midi():
    assert CONTROL_MODES == ('MIDI', 'DMX')          # MIDI first: today's behaviour is the default


def test_dmx_defaults_are_usable():
    assert DMX_CHANNELS == 512
    assert 1 <= DMX_REFRESH_HZ <= 44                 # DMX512 can't carry full frames faster than ~44 Hz
    assert ipaddress.ip_address(DMX_DEFAULT_NODE_IP).version == 4   # Art-Net is IPv4 only
