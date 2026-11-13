# Design: a pull-model frame clock (D3 prep 3)

## Scope
`DMXOutput` asks a *frame source* for the base layer on every tick instead of having content pushed into the
universe from elsewhere. One monotonic clock, owned by `DMXOutput`, gives every frame a time, so animation (fades,
D4 modulation, D6 playback) and output share a time base. The override layer (testers) is unchanged. Out of scope:
moving `DMXOutput` to its own thread (prepared for, not done), scenes themselves, changing the 40 Hz rate.

## Interfaces
```python
# src/pylzr/dmx/clock.py  (pure)
@dataclass(frozen=True)
class FrameTime:
    seconds: float      # since start(); monotonic, never jumps back
    frame:   int        # 0, 1, 2, … since start()
    dt:      float      # seconds since the previous frame (0 for the first)

class FrameClock:                               # wraps time.perf_counter; injectable for tests
    def __init__(self, now: Callable[[], float] = time.perf_counter)
    def start(self) -> None
    def tick(self) -> FrameTime

# src/pylzr/dmx/dmx_output.py
FrameSource = Callable[[FrameTime], Mapping[int, int] | None]   # {DMX channel 1–512: value}; None = no change
SOURCE_BUDGET_MS = 10                                             # a source slower than this is counted and logged

class DMXOutput:
    frame_overrun = pyqtSignal(int)                               # consecutive over-budget frames (diagnostics)
    def set_frame_source(self, source: FrameSource | None) -> None
    def _tick(self) -> None:
        # t = clock.tick(); values = source(t) if source else None
        # if values is not None: universe.set_channels(values)      (base layer)
        # send universe.frame() (base with overrides applied), status, pings as today

# src/pylzr/dmx/universe.py
def set_channels(self, values: Mapping[int, int]) -> None        # base layer, 1-based keys, validated like set_range
```
Ownership: `DMXOutput` owns the clock and the source slot. `App` installs the source (D3's `ScenePlayer.frame`). The
source must be a plain callable that touches no widget, so it can later run on an output thread unchanged. The
tester keeps `set_test_values` (override layer wins, as today).

## Threading / timing
- Today everything stays on the GUI thread: the 25 ms `PreciseTimer` calls `_tick`, which calls the source
  synchronously, merges, sends. Budget per tick: source ≤ 10 ms, merge + send ≤ 0.1 ms (measured 1 µs for the merge
  and packet build, 0.18 ms for rendering two Gruolins), leaving room for the GUI.
- Overrun handling: a slow source doesn't drop frames (the timer coalesces); the frame goes out late. Consecutive
  overruns are counted and logged once per run at WARNING, and emitted for the Performance row.
- Clock: `perf_counter`-based, started in `start()`, so `seconds` restarts at 0 on each `start()`; fades and playback
  key off `FrameTime`, never off wall-clock. `dt` is the real spacing (jitter visible to the source), so a fade that
  spans N frames stays the right length in seconds even when a frame is late.
- Prepared for a thread: `DMXOutput` already uses only `QObject`, a `QTimer` and a socket. Moving it is
  `moveToThread` + making `set_test_values`/`set_frame_source`/`configure` queued, with the source reading content
  through an immutable snapshot (D3's player publishes one per change). Not in this step.

## Failure modes
| Failure | Safe state |
|---|---|
| Source raises | the exception is caught in `_tick`: logged once, the base layer is left as it was, the frame still goes out; after `MAX_SOURCE_FAILURES` (3) in a row the output calls the emergency stop (blackout, stopped) |
| Source returns a channel outside 1–512 or a value outside 0–255 | `ValueError` from `set_channels` → treated as a source failure (above) |
| Source returns `None` | hold the current base layer (a static look needs no re-render) |
| No source installed | base layer stays whatever `set_range` left (today's behaviour: dark) |
| Overrun | late frame, counted, never skipped; the node's own refresh fills the gap |
| Clock source goes backwards (injected test clock) | `dt` clamped to 0, `seconds` never decreases |

## Migration (each step leaves the app working)
1. `clock.py` + `FrameTime`, with unit tests against an injected `now`.
2. `DMXUniverse.set_channels` (`universe.py:44-47` has `set_range`; this is its dict form), tested like it.
3. `DMXOutput`: clock started in `start()` (`dmx_output.py:145-154`); `_tick` (`:188-194`) pulls from the source before
   `_send(self.universe.frame())`; `set_frame_source`; overrun counting; failure counting → `panic()` from the safety
   phase. No caller yet, so every existing DMX test passes unchanged.
4. Diagnostics: `frame_overrun` wired to the Performance row by the window (or `App`), next to FFT rate.
5. D3 installs `ScenePlayer.frame` as the source; the attribute tester keeps the override layer.

## Tests
CI: injected clock → `FrameTime` sequence; a source called once per tick with increasing `frame`; a source returning
`{1: 200}` changes frame bytes; a raising source three times → blackout and stopped; an over-budget source (sleep in
the fake) counts an overrun; overrides still win over the base. Hardware: none beyond watching a fade later in D3.

## Dependencies
Builds on the safety phase (`panic()`), is installed by the app object, and is what `d3-scenes.md` renders through.

## Open questions
- **Q1.** Move `DMXOutput` to its own thread now (so a frozen GUI never stalls frames) or after D3 proves the pull
  model? The design keeps it possible either way.
- **Q2.** Over-budget policy: log and count only, or also fall back to holding the base layer when a source is slow
  three ticks running?
- **Q3.** 40 Hz stays? Some nodes are happier at 44; Art-Net allows up to ~44 full frames/s. Leave the constant.
- **Q4.** Should `FrameTime.seconds` restart on every `start()` (simple, proposed) or keep counting across
  stop/start so a show's clock is continuous?
