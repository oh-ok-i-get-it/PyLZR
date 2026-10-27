import gc

import pytest
import rtmidi as fake_rtmidi

from pylzr.midi import MIDIOutput
from pylzr.midi.midi_output import VIRTUAL_LABEL

from helpers import wait_for_note_offs, wait_until

# MIDIOutput doesn't need a QApplication today; tests that wait use the Qt
# event loop so they keep working if note-offs move to a QTimer.
pytestmark = pytest.mark.usefixtures('qapp')


def connect(m: MIDIOutput) -> MIDIOutput:
    m.open(m.default_port())
    return m


def test_starts_disconnected():
    m = MIDIOutput()
    assert not m.connected
    assert m.port_label is None
    assert m.port_name == 'Not connected'


@pytest.mark.parametrize('os_name, expected', [
    ('win', ['Microsoft GS Wavetable Synth']),
    ('mac', [VIRTUAL_LABEL, 'IAC Driver Bus 1']),
])
def test_list_ports(os_name, expected):
    fake_rtmidi.reset(os_name)
    assert MIDIOutput().list_ports() == expected


def test_mac_defaults_to_own_virtual_port_not_first_system_port():
    m = connect(MIDIOutput())
    assert m.connected and m.port_label == VIRTUAL_LABEL
    assert fake_rtmidi.live_virtual == ['PyLZR-MIDI']


def test_windows_without_loopmidi_stays_disconnected():
    fake_rtmidi.reset('win')
    m = connect(MIDIOutput())
    assert not m.connected       # never falls back to the GS Wavetable synth


def test_named_port_preferred_on_every_os(os_name):
    fake_rtmidi.ports.append('PyLZR-MIDI 1')    # e.g. a loopMIDI port
    m = connect(MIDIOutput())
    assert m.port_label == 'PyLZR-MIDI 1'
    assert fake_rtmidi.live_virtual == []


def test_press_note_sends_on_then_off(os_name):
    fake_rtmidi.ports.append('PyLZR-MIDI 1')
    m = connect(MIDIOutput())
    m.press_note(64)
    wait_for_note_offs()
    assert fake_rtmidi.sent == [('PyLZR-MIDI 1', [0x90, 64, 112]),
                                ('PyLZR-MIDI 1', [0x80, 64, 0])]


def test_press_note_is_noop_while_disconnected():
    fake_rtmidi.reset('win')
    m = connect(MIDIOutput())
    m.press_note(64)
    assert fake_rtmidi.sent == []


def test_switching_port_drops_pending_note_off():
    m = connect(MIDIOutput())
    m.press_note(64)
    m.open('IAC Driver Bus 1')
    m.press_note(65)
    # Note 65's OFF is due after note 64's would have been, so once it arrives
    # note 64's OFF has had its chance
    wait_until(lambda: ('IAC Driver Bus 1', [0x80, 65, 0]) in fake_rtmidi.sent)
    assert fake_rtmidi.sent == [('PyLZR-MIDI', [0x90, 64, 112]),
                                ('IAC Driver Bus 1', [0x90, 65, 112]),
                                ('IAC Driver Bus 1', [0x80, 65, 0])]


def test_virtual_port_released_on_switch_and_reopenable():
    m = connect(MIDIOutput())
    m.open('IAC Driver Bus 1')
    gc.collect()
    assert fake_rtmidi.live_virtual == []
    assert m.open(VIRTUAL_LABEL)
    assert fake_rtmidi.live_virtual == ['PyLZR-MIDI']


def test_open_missing_port_fails_cleanly():
    m = connect(MIDIOutput())
    assert m.open('No Such Port') is False
    assert not m.connected and m.port_name == 'Not connected'


def test_close_releases_port():
    m = connect(MIDIOutput())
    m.close()
    gc.collect()
    assert not m.connected and fake_rtmidi.live_virtual == []
    m.close()   # safe to call twice


def test_toggle_sound_mode():
    m = MIDIOutput()
    assert m.sm_ON is False
    m.toggle_sm()
    assert m.sm_ON is True
    m.toggle_sm()
    assert m.sm_ON is False
