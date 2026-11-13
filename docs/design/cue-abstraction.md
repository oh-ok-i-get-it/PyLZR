# Design: cues instead of MIDI note numbers (D3 prep 1)

## Scope
Sound mode and the keyboard stop producing MIDI note integers and produce a `Cue`. The MIDI output owns the cue→note
table (today's `MODE_MAP` and the key table), so MIDI bytes stay identical. The DMX output accepts cues and hands them
to whatever D3 installs (a scene map); until then it logs them. Out of scope: scenes themselves, any change to which
cues exist, the dual-mode timing, the GUI.

## Interfaces
```python
# src/pylzr/core/cues.py  (pure)
@dataclass(frozen=True)
class ModeCue:                 # from sound mode
    low:  int                  # 0–3
    high: int                  # 0–3
    dual: bool                 # dual mode on for this cue

@dataclass(frozen=True)
class KeyCue:                  # from the keyboard
    index: int                 # 0–47, the key's position in key_map._KEYS
    name:  str                 # '1', 'q', 'SPACE', … for logs

Cue = ModeCue | KeyCue

class CueOutput(Protocol):     # replaces core.protocols.NoteOutput
    def send(self, cue: Cue) -> None: ...

# src/pylzr/core/output_switch.py  — unchanged shape, CueOutput instead of NoteOutput, send() instead of press_note()

# src/pylzr/midi/midi_output.py
MODE_NOTES: Mapping[tuple[int, int], int]   # (low, high) → base note; (0, 0) → MIDI_SPACE_NOTE (never offset)
def note_for(cue: Cue) -> int               # ModeCue: base (+ DM_SEMITONE_OFFSET if dual and not SPACE); KeyCue: 60 + index
class MIDIOutput:
    def send(self, cue: Cue) -> None        # note_for(cue) → today's press_note(note) body (Note ON, OFF after 50 ms)

# src/pylzr/dmx/dmx_output.py
class DMXOutput:
    def set_cue_handler(self, handler: Callable[[Cue], None] | None) -> None   # D3's scene map plugs in here
    def send(self, cue: Cue) -> None        # handler(cue) if set and active, else log at DEBUG

# src/pylzr/analysis/sound_mode.py
class SoundMode:                            # MODE_MAP removed; update_mode() builds ModeCue(lm, hm, self.dm_on and not space)
    def __init__(self, low_thresholds, high_thresholds, output: CueOutput, dm_toggle_rate=120)

# src/pylzr/midi/key_map.py
class KeyboardMapper:                       # emits KeyCue(index, name); the note arithmetic moves to note_for()
```
Ownership: `cues.py` is the only place that defines what a cue is. The MIDI table lives with the MIDI output because
it is a MIDI concern; the "SPACE = quiet" rule (`(0, 0)` is never offset by dual mode) moves with it. Logging: the
sound-mode line keeps its text but the `MIDI=<note>` part is logged by `MIDIOutput.send` instead (check
`tests/test_logging.py` for the exact strings asserted).

## Threading / timing
No change: cues are produced on whichever thread runs `_on_spectrum` (GUI today, the analysis thread after D4) and
consumed synchronously by `OutputSwitch.send`. `MIDIOutput.send` keeps the `QTimer.singleShot` note-off, which needs
an event loop on the calling thread; that holds for the GUI thread and for a `QThread` with `exec()`. `DMXOutput.send`
only stores or forwards the cue; the actual DMX change happens on the next tick through the frame source.

## Failure modes
| Failure | Safe state |
|---|---|
| A cue arrives with DMX chosen and no handler installed (before D3) | logged at DEBUG, nothing sent — the universe keeps its base layer |
| `note_for()` gets an out-of-range mode (bug) | `ValueError` → the exception hook (safety phase) → blackout; the table is total for 0–3 so this is a caller bug |
| Handler raises (D3 scene bug) | same hook; D3 decides whether to catch and hold the current scene instead |
| MIDI port closed | `send()` is a no-op, as `press_note()` is today |

## Migration (each step leaves the app working; golden MIDI test unchanged throughout)
1. Add `core/cues.py` and `note_for()` in `midi_output.py`; unit-test `note_for` against every `MODE_MAP` entry and the
   48 keys (table-driven from the current `sound_mode.py:26-31` and `key_map.py:15-32`).
2. `MIDIOutput.send(cue)` calling the existing `press_note(note_for(cue))`; `DMXOutput.send(cue)` logging;
   `OutputSwitch.send`. Keep `press_note` on both for one step so callers still work.
3. `SoundMode.update_mode()` (`sound_mode.py:58-71`) builds a `ModeCue` and calls `output.send`; `KeyboardMapper.handle_key`
   (`key_map.py:45-52`) builds a `KeyCue`. Remove `MODE_MAP` and `_KEY_TO_NOTE`'s note arithmetic.
4. Delete `press_note` and `NoteOutput`; rename `protocols.py` contents; update `main_window.py:65-68` and the test
   doubles (`tests/test_engine.py:15-20` `RecordingOutput` records cues; assert `note_for(cue)` where notes were asserted).
5. `tests/test_pipeline_golden.py` and `tests/test_main_window_dmx.py::test_cues_go_only_to_the_chosen_output` pass
   byte-for-byte.

## Tests
CI only. The golden pipeline file is the contract: same Note ONs in the same order. Add: `note_for` table test; a
`DMXOutput` handler test (handler called once per cue, only while active); `KeyCue` names match the old log text.

## Dependencies
Builds on the safety phase (exceptions in `send` go to the hook). `app-object.md` wires the switch; `d3-scenes.md`
installs the DMX handler.

## Open questions
- **Q1.** In DMX mode, should keyboard cues map to scenes by key (48 slots) or be ignored? Affects whether `KeyCue`
  needs anything beyond `index`.
- **Q2.** Should `ModeCue` carry the averages that produced it (for D4's modulation and for logging)? Cheap to add
  now, awkward later.
- **Q3.** Keep the `Tone.MODE` log line format (`SoundMode: LOW=2 HIGH=0 | DualMode=2 | MIDI=82`) exactly, or drop the
  `MIDI=` part from sound mode's line now that it doesn't know the note?
