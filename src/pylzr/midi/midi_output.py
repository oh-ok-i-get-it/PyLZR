import threading
import rtmidi as midi
from ..core import MIDI_PORT_NAME
from ..core import text_styles as txt
from ..core.app_logger import logger

# Backends that can create their own virtual port (CoreMIDI, ALSA, JACK).
# Windows MultiMedia cannot — a loopback driver such as loopMIDI must provide
# a port named MIDI_PORT_NAME instead.
_VIRTUAL_APIS = {midi.API_MACOSX_CORE, midi.API_LINUX_ALSA, midi.API_UNIX_JACK}

VIRTUAL_LABEL = f'{MIDI_PORT_NAME} (virtual)'


class MIDIOutput:
    """MIDI output port with sound-mode state.

    Port selection is the same on every OS:
      1. an existing port whose name contains MIDI_PORT_NAME (e.g. a loopMIDI
         port on Windows, which appears as 'PyLZR-MIDI 1'), else
      2. a virtual port named MIDI_PORT_NAME, if the backend supports one.
    Starts disconnected — call open(default_port()) to connect. While
    disconnected press_note() is a no-op. list_ports()/open() let the UI pick
    any other port.

    press_note() sends a Note ON followed by a Note OFF after 50 ms.
    toggle_sm() flips the sm_ON flag used by KeyboardMapper and SoundMode.
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

        self.sm_ON = False

        self._SM_ON_TXT    = txt.RESET + txt.B + txt.GREEN
        self._SM_ON_TXT_B  = txt.B + txt.GREENB + txt.BLACK
        self._SM_OFF_TXT   = txt.RESET + txt.B + txt.RED
        self._SM_OFF_TXT_B = txt.B + txt.REDB + txt.BLACK

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
                logger.info(f'MIDI: opened "{label}"')
                return True
            except (ValueError, NotImplementedError, midi.RtMidiError) as e:
                logger.error(f'MIDI: could not open "{label}": {e}')

        hint = '' if self.supports_virtual else \
            f' — create a port named "{MIDI_PORT_NAME}" in loopMIDI, then reopen Settings'
        logger.warning(f'MIDI: no output port{hint}')
        return False

    def close(self):
        if self.midiout is not None:
            self.midiout.close_port()
            self.midiout = None
            logger.info(f'MIDI: closed "{self.port_label}"')
        self.connected  = False
        self.port_label = None
        self.port_name  = 'Not connected'

    def press_note(self, note: int):
        out = self.midiout
        if out is None:
            return
        NOTE_ON  = 0x90
        NOTE_OFF = 0x80
        out.send_message([NOTE_ON, note, 112])

        def send_off():
            # Skip if the port was switched or closed in the meantime
            if self.midiout is out:
                out.send_message([NOTE_OFF, note, 0])

        t = threading.Timer(0.05, send_off)
        t.daemon = True
        t.start()

    def toggle_sm(self):
        if self.sm_ON:
            print(f"\n{self._SM_OFF_TXT}#### {self._SM_OFF_TXT_B}SOUND MODE OFF{self._SM_OFF_TXT} ####\n{txt.RESET}")
            logger.info('Sound mode: OFF', '#e74c3c')
        else:
            print(f"\n{self._SM_ON_TXT}#### {self._SM_ON_TXT_B}SOUND MODE ON{self._SM_ON_TXT} ####\n{txt.RESET}")
            logger.info('Sound mode: ON', '#2ecc71')
        self.sm_ON = not self.sm_ON
