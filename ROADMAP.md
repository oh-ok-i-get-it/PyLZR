# PyLZR roadmap

The phases, in order, with what each one adds and what it rests on. Design notes for the bigger pieces are in
`docs/design/`; the current step-by-step work plan is `PLAN.md`. Updated 13 Nov 2026 from the D2 plan, the audit
(12 Nov 2026, `docs/AUDIT.md`, which tracks every item's decision) and the decisions below.

## Done

| Phase | Shipped as | What it added |
|---|---|---|
| D0 | v0.3–v0.4 | Sound mode over MIDI (4×4 mode matrix, dual mode), keyboard cues, waveform/spectrum display, saved settings, Windows support, CI on three OSes, the golden pipeline test |
| D1 | v0.5.0 | DMX over Art-Net: packets, universe (base + override layers), UDP sender, `DMXOutput` streaming at 40 Hz with status, Control Mode MIDI/DMX, the channel tester |
| D1.5 | v0.5.0 | Node discovery (ArtPoll/ArtPollReply), "answered" indicator, Find menu |
| D2 parts 0–10 | on `hayden/components-pt3` | The pure `pylzr/fixtures/` package (attributes, vocabulary, OFL profiles, mappings, patterns, bindings, renderer, patch/Rig, library), the shipped Gruolin profile + binding, Fixtures list in Settings, the tester in tabs, the Attributes tab |
| GUI restyle, wireframe pass, finishing touches | same branch | Theme tokens, style roles, reusable widgets, bundled fonts and icons, plot polish |

## Next

### D2 remainder → v0.6.0
- **Component 11, the Patterns tab** (`gui/pattern_library.py`). Part 1 (audit I5): move `_PatternCell` out of
  `gui/attribute_tester.py` into `gui/pattern_cell.py` and replace the three wheel-guard subclasses with one event
  filter, no behaviour change; the Patterns tab reuses the cell. Then: browse by group + number live, tag with name,
  category and 1–5 scale levels, save through `library.save_binding` (your copy), list with edit and delete. Hardware
  check: tags survive a restart.
- **Component 12, docs + v0.6.0:** README "Fixtures and patterns" section, `docs/fixtures.md` format reference,
  version bump in pyproject, README and `uv.lock`. This file replaces the "roadmap backup".

### D2.5: fail-safe output (new, before anything runs unattended) — `docs/design/safety-phase.md`
Adopted from the audit: P2 (blackout before shutdown can block), P3 (blackout sent three times), P1 (exception hook
with an emergency stop), P5 (debounced settings writes), P7 (cue logic before display redraws), all done; then P4
(notice an audio stall: warning, audio dot red, quiet cue; Task 6) and P6 (start without an input device; Task 7).
Plus one hardware check: what the CR011R does when DMX stops (hold the last frame, or go dark), noted in the
README.

### D3 prep: three refactors with no behaviour change
1. **Cues instead of MIDI note numbers** — `docs/design/cue-abstraction.md`. Sound mode and the keyboard emit a
   `Cue`; the MIDI output keeps the note table; the DMX output gets a cue→scene hook.
2. **A non-GUI app object** — `docs/design/app-object.md`. Owns the subsystems and their wiring; `MainWindow`
   becomes a view. Enables headless use and scene tests without a window. Audit I10 (build `library.rig()` once per
   fixtures refresh) folds in here.
3. **A pull-model frame clock** — `docs/design/frame-clock.md`. `DMXOutput` asks a frame source for the base layer
   on every tick, with one monotonic clock for animation and output.

### D3: scenes → v0.7.0 — `docs/design/d3-scenes.md`
Named looks written in attributes (per fixture or for every fixture), a cue→scene map, playback through the frame
source, sound mode and the keyboard driving DMX with no other lighting software. Mirroring/targeting several
fixtures. The `blackout` event.

### D4: dynamic sound mode → v0.8.0 — `docs/design/d4-dynamic-sound-mode.md`
First, benchmarks behind `PYLZR_BENCH=1` (audit I8), so the next two are measured. Then the analysis worker thread
(audit I1, with the chunk-queue bound, audit P8, and the audio-stall check moved onto it) and a 1024-sample hop with a
2048-sample window (audit I7). Then per-hop features (band energies, level, onsets) that nudge attributes such as
speed, size or position within a scene, while big changes still switch scenes.

### PyQt6 spike (before D6)
A branch that builds the app on PyQt6: enum namespaces, `exec()`, pyqtgraph on Qt6, the stylesheet and `set_role`
unchanged. Decides whether D6's timeline UI is built on Qt 5 or 6.
Also re-check that `SettingsStore`'s `QSettings` subclass still holds back Qt's automatic write (it ignores the
`UpdateRequest` event Qt 5.15 posts itself; design Q14): the two pinning tests in `tests/test_settings_store.py`,
`test_a_change_waits_for_the_flush_timer` and `test_many_changes_are_written_once_on_flush`, must still pass.

### D6: timecoded shows → v0.9.0 — `docs/design/d6-timecode-shows.md`
Program looks against an audio file (or import them from a DAW) and play them back in sync.

### D5: auto-binding standard OFL lasers — `docs/design/d5-auto-binding.md`
Draft a binding from any OFL profile by capability type, pattern-request fallbacks, and an on-screen coverage
report. Moved after D6: it has no user until a second laser exists. Pull it forward when one is bought.

### D7: machine learning → v1.0 — `docs/design/d7-machine-learning.md`
Train on D6 shows plus D4 features so the live sound-reactive output reacts the way the shows were programmed.

## Folded into other work
Small audit items with no phase of their own (`docs/AUDIT.md` has the details):
- **I6** (one combo fill/select helper in `widgets.py`; status details as `ElidedLabel`s) and **I9** (pyqtgraph's
  `antialias` option set in `style.apply`): component 11, in part 1's tidy-up next to I5, before the Patterns tab is
  built on those files.
- **P11** (stop node discovery's 50 ms drain timer when nothing is listening): D3 prep 2, when the app object takes
  over discovery and the DMX output's "watching" state.
- **P10** (re-read only changed fixture files on reload): with D5, when a second laser (and more bindings) arrives;
  earlier only if the Settings reload becomes noticeable.
- **P13** (code used only by tests): decided after component 11, which may use `Renderer.defaults` and
  `PatternChannel.allows`; whatever is still unused is removed in component 12.

## Cut
- **The C++ rewrite.** Measured hot paths are 1–180 µs (12 Nov audit); latency comes from the 46 ms chunk, the
  averaging window and GUI-thread coupling, which D4's first two components fix in Python.

## Standing decisions
| Topic | Decision |
|---|---|
| Content speaks only attributes | Scenes, modulations, shows and the model never use channel numbers; a binding turns attributes into DMX |
| Core attribute list | What any laser could do; one laser's extras are `x_…` attributes in its binding |
| Profiles | OFL format, read-only subset; 16-bit and matrix fixtures refused with a clear message |
| Layers | `a`, `b`, … by channel offset; whole-fixture attributes (power, blackout) never shift |
| Safety rules | Every value a mapping can send lies on a described segment; never Maintenance; NoFunction only for off values; testers use the override layer only |
| Data files | Versioned JSON, strict loading with exact places in errors, atomic stable saves, user files never overwritten by updates |
| Folders | Shipped files in the package; yours in `<config>/PyLZR/fixtures/` next to `PyLZR.ini`; `patch.json`, `vocabulary.json`, later `scenes.json` and shows there too |
| Pattern tags | Category + named scales at 5 levels stored as 0.2–1.0; starter lists plus yours |
| Output while unattended | Any abnormal exit tries to black out first; blackout frames are repeated; audio that stops gives the quiet cue, not a held look; the GUI never sits between audio and cues once D4 lands |
| Toolkit | PyQt5 until the PyQt6 spike decides otherwise, before D6 |
| Working method | One component at a time, a stop for review and a commit message after each; suite ×3 + ruff; golden files regenerated only on purpose |
