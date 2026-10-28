from collections.abc import Mapping

from .protocols import NoteOutput


class OutputSwitch:
    """A NoteOutput that forwards every note to one of several named outputs
    (e.g. {'MIDI': midi_out, 'DMX': dmx_out}) — the app's Control Mode.

    Whatever produces notes (sound mode, keyboard) holds the switch instead
    of a specific output, so changing mode never touches them.
    """

    def __init__(self, outputs: Mapping[str, NoteOutput], active: str):
        if not outputs:
            raise ValueError('OutputSwitch needs at least one output')
        self._outputs = dict(outputs)
        self._active = ''
        self.select(active)

    @property
    def names(self) -> list[str]:
        return list(self._outputs)

    @property
    def active(self) -> str:
        return self._active

    @property
    def current(self) -> NoteOutput:
        return self._outputs[self._active]

    def select(self, name: str):
        """Send notes to the output called `name` from now on."""
        if name not in self._outputs:
            raise KeyError(f'no output called {name!r} (have: {", ".join(self._outputs)})')
        self._active = name

    def press_note(self, note: int):
        self.current.press_note(note)
