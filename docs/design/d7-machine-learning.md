# Design: D7 machine learning

## Scope
Learn from programmed shows (D6) how attributes and scene choices follow the audio, and apply that live: given recent
audio features, propose the next scene and the modulation amounts, so the live output reacts the way the shows were
built by hand. Everything the model produces is attributes and scene names, never channel values, so bindings and
safety rules still gate the output. Out of scope: training inside the app (an offline script), GPU requirements, any
audio model beyond PyLZR's own features, cloud anything.

## Interfaces
```python
# src/pylzr/ml/dataset.py  (pure, numpy; optional extra 'ml')
@dataclass(frozen=True)
class Example:
    features: np.ndarray        # (window, F): the last `window` Features rows (low, high, level, onset, …)
    scene:    str               # the scene active at the end of the window ('' if none)
    state:    np.ndarray        # (A,): the rendered attribute state at the end, core attributes in CORE order,
                                # unset = NaN, options one-hot in a fixed table
def build_dataset(show: Show, book: SceneBook, features: Sequence[Features], window: int) -> list[Example]
def export(examples, path: Path) -> None   # .npz; import for training

# src/pylzr/ml/model.py
class Model(Protocol):
    name: str; version: int; window: int; scenes: tuple[str, ...]
    def predict(self, features: np.ndarray) -> Prediction           # (window, F) → next look
@dataclass(frozen=True)
class Prediction:
    scene:      str | None      # None: keep the current scene
    confidence: float           # 0–1
    state:      Mapping[str, float]   # continuous/bipolar attribute nudges (same space as D4 modulation output)
def load_model(path: Path) -> Model                                # format Q2; refuses a model for a different scene book

# src/pylzr/show/ml_source.py
class MLDriver:                                  # sits between the analysis worker and the ScenePlayer
    def __init__(self, model: Model, scenes: ScenePlayer, book: SceneBook, threshold: float = 0.7, hold: float = 2.0)
    def on_features(self, f: Features) -> None    # keeps the window; calls model.predict every `stride` hops
    def apply(self, fixture, state, t) -> dict    # like Modulator.apply: the model's nudges, depth-limited
    def enabled(self) -> bool; def set_enabled(self, on: bool)

# scripts / entry point
pylzr-train <dataset.npz>... -o model.<ext>      # offline; 'ml' extra: numpy + scikit-learn (Q1); torch only if Q1 says so
```
Ownership: `App` owns the driver and installs it as a cue source (scene proposals go through `ScenePlayer.go` with the
same fades) and as a modulation contributor. The user switches between "Sound mode" (4×4 cues), "Dynamic" (D4) and
"Learned" (D7) in Settings; manual cues from the keyboard always win and pause the driver for `hold` seconds.

## Threading / timing
`on_features` runs on the analysis thread; `predict` must return in < 5 ms (a small MLP or gradient-boosted model on a
few hundred inputs; measured before adoption) or it runs every N-th hop. Predictions cross to the player's thread as
an immutable `Prediction` through a queued call, like cues. `apply` runs in the frame source with the D4 budget.
Training is a separate process; the app only loads a finished model file.

## Failure modes
| Failure | Safe state |
|---|---|
| Model file missing, wrong version, or for another scene book | driver disabled with a message; sound mode as before |
| `predict` raises or exceeds its budget 3× running | driver disabled, logged once, blackout not needed (the scene holds) |
| Prediction names an unknown scene | ignored (like a cue with no scene) |
| Nudges outside range | clamped by attribute validation, then binding limits, as D4 |
| Low confidence | below `threshold`: keep the current scene; nudges scaled by confidence |
| Dataset with mismatched feature layout (older hop/feature set) | export carries `feature_names` and `hop`; training refuses mixed sets |

## Migration (each step leaves the app working)
1. Dataset export from a show + its features: replay the show's audio through `FeatureExtractor` offline (no device),
   align with events, write `.npz`. Pure, tested.
2. Baseline model: scene classification + per-attribute regression with scikit-learn, trained by `pylzr-train`;
   report accuracy on a held-out show. No app change yet.
3. `MLDriver` behind the Settings switch, threshold and hold; hardware check: play a known track, compare with the
   hand-made show.
4. Live recording of a performance into a show (if D6 Q6 is yes) so every gig adds data.
5. README; v1.0.

## Tests
CI: dataset alignment on a scripted show (exact rows); model loading refusals; driver threshold/hold logic with a
stub model; budget enforcement with a slow stub; the frame-source path with a stub prediction. Hardware: side-by-side
with a programmed show on the Gruolin, judged by eye; a track the model never saw.

## Dependencies
D3 (scenes), D4 (features, modulator, analysis thread), D6 (shows as training data). The `ml` extra keeps the base
install free of ML dependencies.

## Open questions
- **Q1.** Framework: scikit-learn (small, CPU, pickled models) or PyTorch (sequence models, heavier)? Decides the
  model file format and the install size.
- **Q2.** Model file format and where it lives (`<fixtures>/models/`?), and whether a model is tied to one scene book
  or maps to categories so it survives scene edits.
- **Q3.** Target: predict the scene only, the attribute nudges only, or both from the start?
- **Q4.** How much data is enough: how many shows do you expect to program before this is worth building?
- **Q5.** Is D7 still the goal after D6, or does D6 plus D4 cover what the shows were for?
