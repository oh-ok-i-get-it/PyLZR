"""In-memory stand-in for python-rtmidi 1.5.x used by the test suite.

Mirrors the behaviour PyLZR depends on (checked against python-rtmidi 1.5.8):
- the Windows MultiMedia backend raises NotImplementedError from
  open_virtual_port(); CoreMIDI/ALSA/JACK support virtual ports
- one MidiOut can open only one port, and a virtual port is released only
  when its MidiOut instance is deleted

test_dependency_contract.py checks that every name used here exists in the
real package.
"""

API_UNSPECIFIED  = 0
API_MACOSX_CORE  = 1
API_LINUX_ALSA   = 2
API_UNIX_JACK    = 3
API_WINDOWS_MM   = 4
API_RTMIDI_DUMMY = 5
API_WEB_MIDI     = 6


class RtMidiError(Exception):
    pass


class InvalidPortError(RtMidiError, ValueError):
    pass


class InvalidUseError(RtMidiError, RuntimeError):
    pass


class UnsupportedOperationError(RtMidiError, RuntimeError):
    pass


# ── Simulated system state (reset per test via reset()) ──────────────────────

_DEFAULT_PORTS = {
    'win': ['Microsoft GS Wavetable Synth'],
    'mac': ['IAC Driver Bus 1'],
}

api          = API_MACOSX_CORE
ports        = []   # system output port names, in index order
sent         = []   # (port_name, message) for every send_message call
live_virtual = []   # names of virtual ports that currently exist


def reset(os_name: str = 'mac'):
    """Simulate a fresh system: 'win' (WinMM) or 'mac' (CoreMIDI)."""
    global api
    api = API_WINDOWS_MM if os_name == 'win' else API_MACOSX_CORE
    ports[:] = _DEFAULT_PORTS[os_name]
    sent.clear()
    live_virtual.clear()


reset()


class MidiOut:
    def __init__(self):
        self._port = None   # None = closed, -1 = virtual, else port index
        self._name = None

    def get_current_api(self):
        return api

    def get_ports(self):
        return list(ports)

    def is_port_open(self):
        return self._port is not None

    def open_port(self, port=0, name=None):
        if self._port is not None:
            raise InvalidUseError('A port is already open')
        if not 0 <= port < len(ports):
            raise InvalidPortError(f'Invalid port number: {port}')
        self._port = port
        self._name = ports[port]
        return self

    def open_virtual_port(self, name=None):
        if api == API_WINDOWS_MM:
            raise NotImplementedError('Virtual ports are not supported by the Windows MultiMedia API.')
        if self._port is not None:
            raise InvalidUseError('A port is already open')
        self._port = -1
        self._name = name or 'RtMidi virtual output'
        live_virtual.append(self._name)
        return self

    def close_port(self):
        # Like the real library: closing does not release a virtual port
        if self._port != -1:
            self._port = None

    def send_message(self, message):
        if self._port is None:
            raise InvalidUseError('No port open')
        sent.append((self._name, list(message)))

    def __del__(self):
        if self._port == -1 and self._name in live_virtual:
            live_virtual.remove(self._name)
