import threading

import rtmidi as midi
from PyQt5.QtCore import QTimer
from ..core import MIDI_PORT_NAME
from ..core.app_logger import get_logger

log = get_logger('midi')

# Backends that can create their own virtual port (CoreMIDI, ALSA, JACK).
# Windows MultiMedia cannot — a loopback driver such as loopMIDI must provide
# a port named MIDI_PORT_NAME instead.
_VIRTUAL_APIS = {midi.API_MACOSX_CORE, midi.API_LINUX_ALSA, midi.API_UNIX_JACK}

VIRTUAL_LABEL = f'{MIDI_PORT_NAME} (virtual)'

_NOTE_LENGTH_MS = 50   # Note OFF follows Note ON after this delay

_NOTE_ON        = 0x90    # channel 1, the only channel PyLZR sends on
_NOTE_OFF       = 0x80
_CONTROL_CHANGE = 0xB0
_ALL_NOTES_OFF  = 123     # controller 123, value 0: release every sounding note on the channel
_VELOCITY       = 112
_PANIC_LOCK_TIMEOUT_S = 0.1   # don't wait longer than this on a send stuck in the driver


class MIDIOutput:
    """MIDI output port (a core.protocols.NoteOutput).

    Port selection is the same on every OS:
      1. an existing port whose name contains MIDI_PORT_NAME (e.g. a loopMIDI
         port on Windows, which appears as 'PyLZR-MIDI 1'), else
      2. a virtual port named MIDI_PORT_NAME, if the backend supports one.
    Starts disconnected — call open(default_port()) to connect. While
    disconnected press_note() is a no-op. list_ports()/open() let the UI pick
    any other port.

    press_note() sends a Note ON followed by a Note OFF after 50 ms (the OFF
    is scheduled on the Qt event loop, so a QApplication must be running).

    panic() is the emergency stop: all notes off, then optionally a note, from
    any thread (sends are serialised by a lock, since rtmidi doesn't promise
    thread safety).
    """

    def __init__(self):
        # Long-lived instance used only to enumerate ports. Opening uses a
        # fresh MidiOut each time, since rtmidi can only release a virtual
        # port by deleting the instance that created it.
        self._probe = midi.MidiOut()
        self.supports_virtual = self._probe.get_current_api() in _VIRTUAL_APIS

        self.midiout    = None
        self.connected  = False
        self.port_label = None            # entry from list_ports() that is open
        self.port_name  = 'Not connected'
        self._send_lock = threading.Lock()   # press_note (GUI thread) vs panic() (any thread)

    def list_ports(self) -> list[str]:
        """Selectable port labels: the virtual port (if supported) + system ports."""
        ports = [VIRTUAL_LABEL] if self.supports_virtual else []
        return ports + self._probe.get_ports()

    def default_port(self) -> str | None:
        for name in self._probe.get_ports():
            if MIDI_PORT_NAME in name:
                return name
        return VIRTUAL_LABEL if self.supports_virtual else None

    def open(self, label: str | None) -> bool:
        """Close the current port and open label (an entry from list_ports())."""
        self.close()
        if label is not None:
            try:
                out = midi.MidiOut()
                if label == VIRTUAL_LABEL:
                    out.open_virtual_port(MIDI_PORT_NAME)
                else:
                    # Resolve by name — port indices can shift between calls
                    out.open_port(self._probe.get_ports().index(label))
                self.midiout    = out
                self.connected  = True
                self.port_label = label
                self.port_name  = label
                log.info(f'MIDI: opened "{label}"')
                return True
            except (ValueError, NotImplementedError, midi.RtMidiError) as e:
                log.error(f'MIDI: could not open "{label}": {e}')

        hint = '' if self.supports_virtual else \
            f' — create a port named "{MIDI_PORT_NAME}" in loopMIDI, then reopen Settings'
        log.warning(f'MIDI: no output port{hint}')
        return False

    def close(self):
        if self.midiout is not None:
            with self._send_lock:             # so panic() never sends on a port being closed
                self.midiout.close_port()
            self.midiout = None
            log.info(f'MIDI: closed "{self.port_label}"')
        self.connected  = False
        self.port_label = None
        self.port_name  = 'Not connected'

    def press_note(self, note: int):
        out = self.midiout
        if out is None:
            return
        with self._send_lock:
            out.send_message([_NOTE_ON, note, _VELOCITY])

        def send_off():
            # Skip if the port was switched or closed in the meantime
            if self.midiout is out:
                with self._send_lock:
                    out.send_message([_NOTE_OFF, note, 0])

        # Runs on this (GUI) thread's event loop; panic() may send from another thread, hence the lock
        QTimer.singleShot(_NOTE_LENGTH_MS, send_off)

    def panic(self, note: int | None = None) -> bool:
        """Emergency stop, from any thread: all notes off (channel 1), then
        `note` if given (Note ON, then at once its Note OFF). The note comes
        last, so nothing sent here releases it afterwards. Does nothing while
        no port is open. Never raises: a failed send is logged and the
        remaining messages are still tried. Returns True if `note`'s Note ON
        was sent."""
        note_sent = False
        try:
            out = self.midiout                               # one read: close() may clear it meanwhile
            if out is None:
                log.debug('MIDI: emergency stop: no port open, nothing sent')
                return False
            messages = [[_CONTROL_CHANGE, _ALL_NOTES_OFF, 0]]
            if note is not None:
                messages += [[_NOTE_ON, note, _VELOCITY], [_NOTE_OFF, note, 0]]
            if not self._send_lock.acquire(timeout=_PANIC_LOCK_TIMEOUT_S):
                log.error('MIDI: emergency stop not sent: another MIDI send is stuck')
                return False
            try:
                for message in messages:
                    try:
                        out.send_message(message)
                        note_sent = note_sent or message[0] == _NOTE_ON
                    except Exception as e:
                        log.error(f'MIDI: emergency stop message {message} not sent: {e}')
            finally:
                self._send_lock.release()
            then = f', then note {note}' if note_sent else ''
            log.warning(f'MIDI: emergency stop sent (all notes off{then})')
        except BaseException:
            log.exception('MIDI: emergency stop failed')
        return note_sent
