# Design: D6 timecoded shows

## Scope
Program looks against an audio file and play them back in sync: a show is a list of timed events (scene changes,
attribute changes with fades, blackouts) per target, plus the audio file it belongs to. Playback drives the same
`ScenePlayer` through the frame clock, with the clock slaved to the audio file's position. Import of events from a
DAW export. Out of scope: audio editing, video, external timecode (LTC/MTC) input, multi-track audio, recording a
live performance into a show (D7 may want it; note it in Q5).

## Interfaces
```python
# src/pylzr/show/show.py  (pure; versioned JSON in <fixtures>/shows/<name>.json)
@dataclass(frozen=True)
class Event:
    t:         float                             # seconds from the audio file's start
    target:    str                               # '*' or fixture name
    kind:      Literal['scene', 'set', 'blackout']
    scene:     str = ''                          # kind 'scene'
    values:    Mapping[str, Any] = {}            # kind 'set': attribute state to merge
    fade:      float = 0.0

@dataclass(frozen=True)
class Show:
    name:     str
    audio:    str                                # path relative to the shows folder
    duration: float
    events:   tuple[Event, ...]                  # sorted by t; validated like scenes
    def at(self, t: float) -> int                # index of the first event after t (bisect)
    def with_event(...); def without(...)

def import_events(path: Path, fmt: Literal['csv', 'midi']) -> tuple[Event, ...]
    # csv: t,target,kind,scene|attr=value,fade ; midi: Note ON on a channel → ModeCue/KeyCue key → scene via the book

# src/pylzr/show/transport.py
class ShowClock(Protocol):                       # the time base during playback
    def position(self) -> float                  # seconds into the audio; monotonic while playing
    def playing(self) -> bool

class AudioFilePlayer(QObject):                  # implements ShowClock; owns the output stream
    position_changed = pyqtSignal(float)         # ~10 Hz for the UI
    finished         = pyqtSignal()
    def load(self, path) -> None; def play(self); def pause(self); def seek(self, t: float); def stop(self)

class ShowPlayer:
    def __init__(self, scenes: ScenePlayer, clock: ShowClock)
    def load(self, show: Show) -> None
    def frame(self, t: FrameTime) -> Mapping[int, int] | None   # installed as the DMX frame source while a show plays:
                                                                # fires every event up to clock.position(), then delegates to scenes.frame
    def seek(self, t: float) -> None             # re-evaluates the look at t: last scene/set per target before t, no fades
```
Ownership: `App` owns the `AudioFilePlayer` and `ShowPlayer`; while a show is loaded, `ShowPlayer.frame` replaces
`ScenePlayer.frame` as the frame source and cues from sound mode are ignored (Q3). GUI: a Show window with a
waveform of the file, an event lane per target, transport buttons, and "capture" (add a `set` event from the
Attributes tab at the playhead). Built after the PyQt6 spike decides the toolkit.

## Threading / timing
- Audio output runs on its own callback thread (PortAudio output stream via PyAudio, which is already a dependency);
  `position()` is computed from frames written minus the stream's output latency, read atomically.
- The DMX tick reads `clock.position()` once per frame and fires events whose `t` ≤ position. Timing error is at most
  one tick (25 ms) plus the output latency estimate error; fades are keyed to `FrameTime` so a late tick doesn't
  stretch them.
- Seek: pause, set position, `ShowPlayer.seek` rebuilds the look, resume. Rebuild is O(events) once.
- The live analysis keeps running (display), but cues don't drive scenes during playback (Q3).

## Failure modes
| Failure | Safe state |
|---|---|
| Audio file missing or undecodable | show loads, playback refused with the path in the message; no DMX change |
| Output device gone mid-show | stream error → `finished`; the look holds; blackout only on stop (Q4) |
| Position jumps backwards (underrun recovery) | events already fired are not refired; `seek` semantics only on an explicit seek |
| Event references a missing scene or fixture | skipped and listed in the show's problems (like patch problems) |
| DAW import with unknown rows | rows reported, valid rows kept, nothing saved until the user confirms |
| Show ends | last look holds until stop; stop → blackout (consistent with leaving DMX mode) |

## Migration (each step leaves the app working)
1. `show.py` model + file + import (CSV first), pure, with tests.
2. `ShowClock` + a `FakeClock` for tests; `ShowPlayer` over the existing `ScenePlayer` (`d3-scenes.md`); golden frames
   for a scripted show with a fake clock.
3. `AudioFilePlayer` on PyAudio output (decode WAV with the standard library; other formats Q1).
4. `App` wiring and a minimal transport UI (load, play, pause, stop, position).
5. The show editor (lanes, capture, drag events) on the chosen toolkit.
6. MIDI-file import; README; v0.9.0.

## Tests
CI: model and import; `ShowPlayer` golden frames with a fake clock (events fire once, in order, at the right frame;
seek rebuilds the look); position maths with a fake stream (latency subtracted). Hardware: a 3-minute track with
scene changes on beats, drift measured against a clap in the audio; seek mid-song.

## Dependencies
D3 (scenes, player), frame clock, app object. The PyQt6 spike precedes the editor. D4 modulations apply during
playback if the show's scenes carry them.

## Open questions
- **Q1.** Audio formats: WAV only (standard library) or MP3/FLAC too (adds a decoder dependency: `soundfile` or
  `miniaudio`)?
- **Q2.** Audio output through PyAudio (already a dependency, exact position maths) or Qt Multimedia (simpler, less
  precise position)?
- **Q3.** During playback, is live sound mode off entirely, or may it still *modulate* (D4) while scene changes come
  from the show?
- **Q4.** On a mid-show audio failure: hold the look or black out?
- **Q5.** DAW import format: CSV from a marker export, a MIDI file with notes = cues, or both?
- **Q6.** Should a live performance (cues + modulations as they happen) be recordable as a show? It would be D7's
  cheapest training data.
