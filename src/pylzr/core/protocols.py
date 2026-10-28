from typing import Protocol


class NoteOutput(Protocol):
    """Anything that can play a note: MIDIOutput today, DMX later."""

    def press_note(self, note: int) -> None: ...
