# Design: D4 dynamic sound mode

## Scope
Small changes in the music nudge attributes inside the current scene (speed, size, position, strobe, …); big changes
still switch scenes through sound mode's cues. Two enabling components first: (1) the analysis worker thread, so cues
and features never wait for the GUI (audit I1); (2) a 1024-sample hop with the 2048-sample window, so features arrive
every 23 ms (audit I7). Out of scope: beat tracking beyond a simple onset, any learned behaviour (D7), a modulation
*editor* beyond a table in Settings, changing the 4×4 mode logic.

## Interfaces
```python
# src/pylzr/core/config.py
HOP = 1024                       # samples between analyses; CHUNK (2048) stays the analysis window

# src/pylzr/analysis/features.py  (pure, numpy)
@dataclass(frozen=True)
class Features:
    t:      float                # seconds since engine start (audio clock: hops × HOP / SAMPLE_RATE)
    low:    float                # band means as today (same scale as the cutoffs)
    high:   float
    level:  float                # peak 0–1 of the hop
    onset:  bool                 # spectral-flux onset in this hop (simple threshold, documented)

class FeatureExtractor:
    def __init__(self, bands: BandLayout, hop: int)
    def push(self, samples: np.ndarray) -> list[Features]       # int16 hop; returns 0 or 1 Features per hop

# src/pylzr/analysis/worker.py  (replaces fft_worker.py)
class AnalysisWorker(QObject):           # lives on its own QThread with an event loop
    spectrum_ready      = pyqtSignal(np.ndarray)         # display
    waveform_ready      = pyqtSignal(np.ndarray)         # display (gain applied)
    level_measured      = pyqtSignal(float, bool)
    features_ready      = pyqtSignal(object)             # Features, every hop
    averages_ready      = pyqtSignal(float, float)
    modes_updated       = pyqtSignal(int, int, int, int)
    @pyqtSlot(np.ndarray, bool) def process(self, chunk, overflowed)   # from the audio callback, queued
    # owns: FeatureExtractor, AudioAnalyzer, SoundMode (cue output is called from this thread)
    # settings slots (queued): set_gain, set_window, set_count_rate, set_sound_mode, set_cutoff

# src/pylzr/engine.py
class AudioEngine(QObject):              # keeps its public signals; forwards from the worker; owns the thread
    features_ready = pyqtSignal(object)

# src/pylzr/show/modulation.py  (pure)
@dataclass(frozen=True)
class Modulation:
    feature:   str               # 'low' | 'high' | 'level' | 'onset'
    attribute: str               # core attribute name, e.g. 'scan_speed' (layered: applies to every layer)
    target:    str = '*'         # fixture name or '*'
    low:       float = 0.0       # feature value mapped to `amount` 0 …
    high:      float = 1.0       # … and this to 1 (clamped)
    depth:     float = 0.5       # how far from the scene's value the attribute may move (fraction of its range)
    smooth:    float = 0.2       # seconds, one-pole smoothing of the feature
    decay:     float = 0.3       # onset only: seconds to fall back

class Modulator:
    def __init__(self, modulations: Sequence[Modulation])
    def update(self, f: Features) -> None                       # called per hop (any thread, under one lock)
    def apply(self, fixture: str, state: dict[AttrKey, Any], t: FrameTime) -> dict[AttrKey, Any]   # used by ScenePlayer.frame

# scenes.json gains "modulations": [...] per scene (default: none) → Scene.modulations: tuple[Modulation, ...]
```
Ownership: `AudioEngine` owns the worker and its thread; `App` connects `features_ready` to the player's modulator;
`ScenePlayer.frame` applies the modulator after the fade interpolation and before rendering, so limits and safety
still hold.

## Threading / timing
- Audio callback (PortAudio thread) → queued `process` on the analysis thread: gain, hop buffering, window, FFT,
  features, analyzer, sound mode, cue `send()`. The GUI thread receives display signals only. `MIDIOutput.send`'s
  note-off `QTimer.singleShot` runs on the analysis thread's event loop; `DMXOutput.send` must post the cue to the
  player's thread (queued), see `d3-scenes.md`.
- Hop 1024 at 44.1 kHz = 23.2 ms per `Features`; the window stays 2048 so bins and the cutoff scale are unchanged
  (the golden file changes only in frame count, not in band values per window: regenerate and review).
- The modulator's `update` runs on the analysis thread and `apply` on the frame-clock thread; one lock around a small
  float snapshot (no allocation per hop). Budget: `update` < 50 µs, `apply` < 100 µs per fixture.
- Queue bound (audit P8, now relevant): the worker drops *display* emits when more than 2 chunks are pending, never
  analysis; a counter shows "late" in Performance.

## Failure modes
| Failure | Safe state |
|---|---|
| Analysis thread raises | exception hook → blackout; the thread's loop continues; FFT rate shows 0 if it died |
| Audio stops (device gone) | no features → modulations decay to 0 → the scene's own values; `fps 0` warning (audit P4 becomes in-scope here) |
| Feature NaN/inf (silence with log scaling bug) | `Features` validates finite numbers; non-finite → hop skipped and counted |
| Modulation names an attribute a fixture lacks | skipped, reported with the scene's `unsupported` |
| Modulated value leaves the range | clamped to the attribute's range before render; binding limits (`limit`, `min`/`max`) then apply |
| GUI frozen | cues and features unaffected; only the display lags (the point of I1) |

## Migration (each step leaves the app working)
1. `AnalysisWorker` = today's `FFTWorker` (`fft_worker.py:33-37`) plus `AudioAnalyzer` and `SoundMode` moved from
   `engine.py:171-188`; the engine forwards signals; settings become queued slots. Update
   `tests/test_engine.py:115-133` (processing thread is now the worker). Golden file unchanged.
2. `HOP`: buffer two hops into the 2048 window; `FeatureExtractor` emits `Features`; `AudioAnalyzer.push` is fed per
   hop (count_rate semantics: frames = hops; the `DM_TOGGLE_FRAMES` constant doubles to keep ~111 s). Regenerate the
   golden file; review the diff (twice the frames, same averages within tolerance).
3. `Modulation`/`Modulator` + scene file field; player applies it; a hand-written modulation on `scan_speed` from
   `level`. Hardware check.
4. Settings UI: a modulation table (feature, attribute, depth, smoothing) on the current scene.
5. README; v0.8.0.

## Tests
CI: feature determinism on `tone_chunks` (exact values per hop in a golden); onset on a step; modulator table tests
(mapping, clamping, smoothing, decay); thread-ownership test; queue-bound test (stall the GUI with a sleep in a slot,
assert no dropped analysis and a counted display drop); the full golden pipeline. Hardware: level → size, high → scan
speed on the Gruolin; a frozen GUI (open a modal) does not stop cues.

## Dependencies
Safety phase, cue abstraction, app object, frame clock, D3 scenes (modulations live on scenes).

## Open questions
- **Q1.** Hop 1024 (23 ms) or 512 (12 ms)? 512 quadruples FFT work (still µs) but halves the averaging resolution
  of `count_rate` unless its range is rescaled.
- **Q2.** Feature set for v1: just `low`, `high`, `level`, `onset`, or also a mid band and spectral centroid?
- **Q3.** Modulations per scene (proposed) or one global table that applies to every scene?
- **Q4.** Should audit P4 (audio-stall warning, quiet cue on silence) be adopted as part of this phase, since the
  worker is where it belongs?
- **Q5.** Should `count_rate` stay in "frames" (now hops) or become seconds in the UI, now that the hop changes?
