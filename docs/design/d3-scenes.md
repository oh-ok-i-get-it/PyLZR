# Design: D3 scenes

## Scope
Named looks written in attributes, a map from cues to scenes, and playback through the frame source, so sound mode
and the keyboard drive the laser directly in DMX mode. Several fixtures: a scene state for `*` applies to every usable
fixture; a named fixture's state overrides it. The `blackout` event. Simple timed fades between scenes (continuous and
bipolar attributes interpolate; options, patterns and power switch at the start). Out of scope: timelines (D6),
sound-driven modulation inside a scene (D4), a scene *editor* beyond "capture what the Attributes tab shows", pattern
fallbacks (D5), MIDI-mode behaviour (unchanged).

## Interfaces
```python
# src/pylzr/fixtures/scenes.py  (pure; same rules as patch.py: versioned, strict, atomic)
@dataclass(frozen=True)
class Scene:
    name:   str                                  # 1–MAX_NAME chars, unique ignoring case
    states: Mapping[str, Mapping[str, Any]]      # target ('*' or fixture name) → {'size': 0.5, 'pos_x@b': -0.2, …}
    fade:   float = 0.0                          # seconds; 0 = cut
    def state_for(self, fixture: str) -> dict[AttrKey, Any]     # '*' merged with the fixture's own entries

@dataclass(frozen=True)
class SceneBook:                                 # scenes.json
    scenes:  tuple[Scene, ...]
    cues:    Mapping[str, str]                   # cue key → scene name; keys 'L2H0' (ModeCue low 2 high 0), 'K17' (KeyCue)
    def scene(self, name: str) -> Scene | None
    def for_cue(self, cue: Cue) -> Scene | None
    def with_scene(self, scene, replacing=None) -> 'SceneBook'; def without(self, name); def with_cue(self, key, name)

def cue_key(cue: Cue) -> str                     # the stable text form used in the file
def load_scenes(data) -> SceneBook; read_scenes(path); write_scenes(path, book)

# src/pylzr/fixtures/library.py
class FixtureLibrary:
    scenes: SceneBook                            # loaded like patch/vocabulary (missing → empty, unreadable → problem)
    def save_scenes(self, book: SceneBook) -> None

# src/pylzr/show/player.py  (Qt-free; drives the frame source)
class ScenePlayer:
    def __init__(self, rig: Rig, book: SceneBook)
    def set_rig(self, rig: Rig) -> None;  def set_book(self, book: SceneBook) -> None
    def go(self, scene: Scene, at: FrameTime) -> None      # start a fade from the current rendered state
    def blackout(self, at: FrameTime) -> None               # 'blackout' event: dark now, fade state cleared
    def on_cue(self, cue: Cue) -> None                      # book.for_cue → go(); unknown → hold (logged at DEBUG once per key)
    def frame(self, t: FrameTime) -> Mapping[int, int] | None   # the FrameSource: None while static and unchanged
    @property
    def current(self) -> Scene | None; def unsupported(self) -> Mapping[str, tuple[AttrKey, ...]]   # per fixture, for the UI
```
Ownership: `App` creates the player, installs `player.frame` as the DMX frame source and `player.on_cue` as the DMX
cue handler, and calls `set_rig`/`set_book` on `fixtures_changed`. GUI: a Scenes tab in the tester window (capture
the Attributes tab's state as a scene, rename, set fade, delete) and a cue grid (4×4 mode cells + the key row) in
Settings → DMX or the tester. The tester's override layer still wins over a playing scene (testing a fixture while a
show runs).

## Threading / timing
`on_cue` and `frame` run on the GUI thread today (cue from `_on_spectrum`, frame from `_tick`). `go()` stores
`(from_render, to_state, t0, fade)` per fixture; `frame(t)` renders each fixture once per tick while a fade runs
(0.085 ms each measured), then returns `None` until the next `go()`. Interpolation is in attribute space (0..1 /
−1..1), then rendered, so binding limits and safety hold at every intermediate frame. Deadline: the source budget from
`frame-clock.md` (10 ms) covers ~50 fixtures; a fade never allocates per frame beyond the render.
After D4 moves cues to the analysis thread, `on_cue` must become a queued call onto the thread that owns the player
(GUI, or the output thread): the player is single-threaded by design.

## Failure modes
| Failure | Safe state |
|---|---|
| Scene names a fixture not in the patch, or an attribute the fixture lacks | skipped and reported in `unsupported`, never an error (renderer's portability rule) |
| Scene has a wrong value (e.g. size 2) | refused at load/save (`Scene.__post_init__` validates against `CORE` kinds); a binding extra it can't check is validated at render → source failure → emergency stop after 3 (a bug, not a user error) |
| Cue with no scene | hold the current look; logged once per cue key |
| Fixture with a patch problem | not rendered (Rig skips it), shown in the Fixtures list as today |
| `scenes.json` unreadable | empty book, problem listed, app runs; saving sets the bad file aside (library rule) |
| Leaving DMX mode / closing | blackout as today; the player's fade state is cleared on `blackout()` |

## Migration (each step leaves the app working)
1. `fixtures/scenes.py` with load/save and `cue_key`; `FixtureLibrary.scenes/save_scenes` (`library.py:124-126, 213-215`
   pattern); architecture test unchanged (still pure).
2. `show/player.py` with cut-only `go()` and `frame()`; golden test of a two-fixture scenario → exact frames.
3. `App` installs the source and the cue handler (`DMXOutput.set_frame_source`, `set_cue_handler`); keyboard and sound
   mode now light the laser in DMX mode with a hand-written `scenes.json`. Hardware check here.
4. Fades (interpolate in attribute space; `fade` per scene).
5. GUI: Scenes tab (capture from `AttributeTester.state()`/`raw_patterns()`, `attribute_tester.py:782-790`), cue grid,
   `blackout` button/key.
6. README section; v0.7.0.

## Tests
CI: scene file round trip and every validation error; `for_cue` keys; player golden frames for cut and fade (injected
`FrameTime`s, exact bytes at t = 0, mid, end); `*` + override merge; unsupported reporting; cue with no scene holds;
window tests: a `ModeCue` in DMX mode changes the frame, in MIDI mode changes nothing. Hardware: two Gruolins, a cue
grid of four scenes, fades look right, the tester still overrides, blackout from the keyboard.

## Dependencies
Cue abstraction (cue keys), app object (ownership), frame clock (source + time). The safety phase's stop handles
source failures.

## Open questions
- **Q1.** Fades in D3, or cut-only first and fades with D4? (Fades are where the frame clock earns its keep.)
- **Q2.** Cue grid scope: only the 16 mode cells + dual (32 looks), or also the 48 keyboard keys? (Cue Q1.)
- **Q3.** Per-layer scenes: is a scene always both layers, or can it leave a layer untouched (today "unset" means the
  fixture's default, and for `pattern` it means dark)?
- **Q4.** Where scenes are edited: a tab in the tester window (reuses the Attributes grid) or a new window?
- **Q5.** Should a scene remember raw (untagged) patterns, or only tagged requests? Raw ties a scene to one laser.
- **Q6.** What does an audio stall do in DMX mode once scenes drive the laser: hold the current scene, play the quiet
  scene (the LOW 0 / HIGH 0 cue's scene, which is what D2.5 Task 6's quiet cue would reach through the cue→scene map
  unchanged), or black out? Until D3, DMX content doesn't follow cues, so a stall changes nothing in DMX
  (`safety-phase.md` Q15). Decide before D3's playback step, since an unattended show with a dead microphone is the
  case it is for.
