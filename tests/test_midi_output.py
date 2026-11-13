import gc
import threading

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


# ── Emergency stop ───────────────────────────────────────────────────────────

ALL_OFF = [0xB0, 123, 0]


def connect_named() -> tuple[MIDIOutput, str]:
    fake_rtmidi.ports.append('PyLZR-MIDI 1')
    return connect(MIDIOutput()), 'PyLZR-MIDI 1'


def test_panic_sends_all_notes_off_then_the_note_on_and_off(os_name):
    m, port = connect_named()
    assert m.panic(106) is True
    assert fake_rtmidi.sent == [(port, ALL_OFF), (port, [0x90, 106, 112]), (port, [0x80, 106, 0])]


def test_panic_without_a_note_sends_only_all_notes_off():
    m = connect(MIDIOutput())
    assert m.panic() is False
    assert [msg for _, msg in fake_rtmidi.sent] == [ALL_OFF]


def test_panic_while_disconnected_sends_nothing():
    fake_rtmidi.reset('win')
    m = connect(MIDIOutput())
    assert m.panic(106) is False
    assert fake_rtmidi.sent == []


def test_panic_keeps_going_when_a_send_fails(caplog):
    m = connect(MIDIOutput())
    real = m.midiout.send_message
    calls = []

    def flaky(message):
        calls.append(message)
        if len(calls) == 1:
            raise fake_rtmidi.RtMidiError('driver hiccup')
        real(message)

    m.midiout.send_message = flaky
    assert m.panic(106) is True
    assert [msg for _, msg in fake_rtmidi.sent] == [[0x90, 106, 112], [0x80, 106, 0]]
    errors = [r for r in caplog.records if r.levelname == 'ERROR']
    assert len(errors) == 1 and '[176, 123, 0]' in errors[0].getMessage()


def test_panic_returns_false_when_the_note_on_fails():
    m = connect(MIDIOutput())
    real = m.midiout.send_message

    def no_note_on(message):
        if message[0] == 0x90:
            raise fake_rtmidi.RtMidiError('driver hiccup')
        real(message)

    m.midiout.send_message = no_note_on
    assert m.panic(106) is False


def test_panic_on_a_port_closed_underneath_does_not_raise(caplog):
    m = connect_named()[0]
    m.midiout.close_port()                 # the fake then raises InvalidUseError on every send
    assert m.panic(106) is False
    assert any(r.levelname == 'ERROR' for r in caplog.records)


def test_panic_from_another_thread():
    m, port = connect_named()
    t = threading.Thread(target=m.panic, args=(106,))
    t.start()
    t.join()
    assert fake_rtmidi.sent == [(port, ALL_OFF), (port, [0x90, 106, 112]), (port, [0x80, 106, 0])]


def test_a_pending_note_off_still_arrives_after_panic():
    m = connect(MIDIOutput())
    m.press_note(64)
    m.panic(106)
    wait_for_note_offs()
    assert [msg for _, msg in fake_rtmidi.sent] == [
        [0x90, 64, 112], ALL_OFF, [0x90, 106, 112], [0x80, 106, 0], [0x80, 64, 0]]
