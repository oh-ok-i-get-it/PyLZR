# PyLZR audit

12 Nov 2026 · branch `hayden/components-pt3` at `c9bb094` · 1313 tests pass, ruff clean.

This file holds the audit as it was written on 12 Nov 2026 (sections 2 to 6 below), with a tracking table added at the
top on 13 Nov 2026. The audit text is unchanged except that the evidence line numbers are those of `c9bb094`, so they
have since moved. The audit gave problems and improvements an ID but no title; the titles in the tracking table are
short labels added for this table (taken from the order-of-attack line and the PLAN.md task headings where there is
one). The audit's own "no PLAN.md or HANDOFF.md in the repo" (P9) was true at `c9bb094`.

## 1. Tracking

Decision: adopted / deferred / folded in / won't do / undecided. Order: the item's place in section 6, the audit's
suggested order of attack.

| ID | Title | Decision | Where | Status | Order |
|---|---|---|---|---|---|
| P1 | Exception hook and emergency stop | adopted | ROADMAP D2.5; PLAN task 3; `docs/design/safety-phase.md`; `docs/plans/task-3-emergency-stop.md` | done (`efa64b9`, review follow-up `c5a2601`) | 3 |
| P2 | Blackout before anything that can block on exit | adopted | ROADMAP D2.5; PLAN task 1; `safety-phase.md` | done (`fdf17d1`) | 1 |
| P3 | Send the blackout three times | adopted | ROADMAP D2.5; PLAN task 2; `safety-phase.md` (Q5 assumption) | done (`25e92de`) | 2 |
| P4 | Detect an audio stall | deferred | Out of scope in `safety-phase.md`; `d4-dynamic-sound-mode.md` says it becomes in scope there, open question Q4 | open | 6 |
| P5 | Debounced settings writes | adopted | ROADMAP D2.5; PLAN task 4; `safety-phase.md`; `docs/plans/task-4-debounced-settings.md` | done (`37c8dc0`) | 4 |
| P6 | Start without an input device | deferred | Out of scope in `safety-phase.md` and `app-object.md` | open | 7 |
| P7 | Cue logic before display redraws | adopted | ROADMAP D2.5; PLAN task 5; `safety-phase.md` | done (`211618f`) | 5 |
| P8 | Bound the chunk queue | folded in | `d4-dynamic-sound-mode.md` (queue bound in the analysis worker, as I1 supersedes it) | planned | 8 |
| P9 | Commit the roadmap | adopted | `ROADMAP.md` | done (`27823d5`) | 10 |
| P10 | Cache the fixture library per file | undecided | none | open | 19 |
| P11 | Stop the discovery drain timer when idle | undecided | none | open | 19 |
| P12 | PyQt6 spike | adopted | ROADMAP "PyQt6 spike (before D6)" | planned | 20 |
| P13 | Remove code used only by tests | undecided | none | open | 18 |
| I1 | Analysis worker thread | folded in | ROADMAP D4 (first component); `d4-dynamic-sound-mode.md` | planned | 14 |
| I2 | Cue abstraction | adopted | ROADMAP D3 prep 1; `docs/design/cue-abstraction.md` | planned | 11 |
| I3 | Non-GUI app object | adopted | ROADMAP D3 prep 2; `docs/design/app-object.md` | planned | 12 |
| I4 | Pull-model frame clock | adopted | ROADMAP D3 prep 3; `docs/design/frame-clock.md` | planned | 13 |
| I5 | Split `_PatternCell` out of the tester | undecided | none | open | 9 |
| I6 | One combo helper, `ElidedLabel` for status details | undecided | none | open | 17 |
| I7 | 1024-sample hop, 2048-sample window | folded in | ROADMAP D4 (second component); `d4-dynamic-sound-mode.md` | planned | 15 |
| I8 | Benchmarks behind `PYLZR_BENCH=1` | undecided | none | open | 16 |
| I9 | Move the pyqtgraph antialias option to `style.apply` | undecided | none | open | 17 |
| I10 | Build `library.rig()` once per `_show_fixtures` | undecided | none (the audit says it folds into I3) | open | 17 |

Items from section 5 (Plan changes) that are not P or I items:

| # | Change | Decision | Where | Status |
|---|---|---|---|---|
| 1 | Insert D2.5 before component 11 | adopted, for P1, P2, P3, P5, P7 only | ROADMAP D2.5; PLAN | in progress; P4, P6, P8 not in it |
| 2 | Component 11: do I5 first; CR011R DMX-loss hardware check | hardware check adopted; I5 undecided | PLAN "After task 5"; ROADMAP D2.5 | open |
| 3 | Component 12 adds `docs/ROADMAP.md` | adopted | ROADMAP D2 remainder | done (`27823d5`) |
| 4 | D3 prep first: I2, I3, I4 | adopted | ROADMAP D3 prep | planned |
| 5 | D4 starts with I1 and I7 | adopted | ROADMAP D4 | planned |
| 6 | Order D3, D4, D6, D5 | adopted | ROADMAP | done in the roadmap |
| 7 | Cut the C++ rewrite | adopted (won't do the rewrite) | ROADMAP "Cut" | done |
| 8 | PyQt6 spike before D6 | adopted | ROADMAP | planned |
| 9 | Keep the strongest parts of the design | n/a | | n/a |

Measured on this machine (median, `src` from source, shipped fixtures only):

| Path | Cost |
|---|---|
| `FixtureLibrary(None)` full reload | 7.1 ms |
| `Renderer.render`, 20 attributes, 2 layers | 0.085 ms |
| `Rig.render`, two Gruolins | 0.18 ms |
| `DMXUniverse.frame()` + `build_artdmx` | 0.001 ms |
| FFT chain (window, rfft, abs, scale) | 0.013 ms |
| `_soften` display smoothing | 0.011 ms |
| `SettingsStore.set` (QSettings sync) | 2.2 ms (max 4.1) |

## 2. Summary

The codebase is in good health: layers are separated and enforced by a test, the pure `fixtures` package is well
designed and exhaustively tested, the DMX transport is careful about network failure modes, and the compute hot paths
are microseconds, so Python is not the latency problem. The real gaps are in **fail-safe behaviour**: on the most
likely abnormal exits (an exception in any Qt slot, a hang during shutdown, a lost blackout datagram, an audio device
that stops) the laser holds its last look rather than going dark, and nothing in the plan addresses this before scenes
(D3) make the output run unattended. The D2 plan is sound and nearly done (parts 0–10 built as specified; 11–12 left);
the D3–D7 roadmap is the right direction but needs three preparatory refactors (a cue abstraction instead of MIDI note
numbers, a non-GUI app object, a pull-model frame clock) and a safety phase inserted before D3. The roadmap itself
lives only in Claude plan files outside the repo and should be committed.

## 3. Problems

| ID | Sev | Area | Evidence | Issue | Fix | Effort |
|---|---|---|---|---|---|---|
| P1 | Crit | Fail-safe | `src/pylzr/__main__.py:7-14`; no `sys.excepthook`/`atexit` anywhere in `src` (grep) | PyQt5 ≥ 5.5 routes an unhandled Python exception in a slot to `qFatal()`, which aborts the process. Every GUI handler, `_tick` and `_process_chunk` are slots. An abort skips `closeEvent`, so no blackout is sent and the node keeps the last frame **[node hold behaviour unverified for the CR011R]**. | Install `sys.excepthook` in `main()` that logs the traceback and calls a module-level "emergency stop" (DMX blackout + stop), then exits cleanly. Register the same stop with `atexit`. Add a test that raises inside a slot and asserts a blackout frame was sent. | S |
| P2 | High | Fail-safe | `src/pylzr/gui/main_window.py:371-378`; `src/pylzr/engine.py:84-92` (`fft_thread.wait()` has no timeout); `src/pylzr/audio/audio_input.py:146-150` | `closeEvent` runs `engine.shutdown()` (PortAudio close + unbounded thread wait) **before** `dmx_out.close()`. If shutdown blocks, the blackout never goes out. | Reorder: `dmx_out.stop()` first (blackout), then the tester, engine, discovery, MIDI, and `dmx_out.close()` last. Give `fft_thread.wait()` a timeout. | S |
| P3 | High | Fail-safe | `src/pylzr/dmx/dmx_output.py:156-163` (stop), `:133-134` (configure) | The blackout is one UDP datagram. One lost packet and the old node holds the last look. | Send the blackout three times (`_send(_BLACKOUT)` ×3, or hold the timer for 2–3 more ticks sending blackout before stopping). Same in `configure()`. Test asserts ≥ 3 dark frames. | S |
| P4 | Med | Fail-safe / RT | `src/pylzr/engine.py:190-195`; `src/pylzr/gui/main_window.py:192-194` | If PortAudio stops calling back (device unplugged, exclusive-mode grab), nothing notices: fps 0 is shown only while Settings is open, never logged, and the audio dot stays green. Sound mode then holds its last cue indefinitely. | In `_report_diagnostics`, when `fps == 0` while `audio.is_active`: log a warning once, emit an audio-status signal (dot red, "no audio"), and have `SoundMode` fall back to the quiet cue after N silent seconds. | S |
| P5 | Med | Real-time | `src/pylzr/gui/main_window.py:164-170`; `src/pylzr/gui/settings_store.py:83-87`; `src/pylzr/gui/control_panel.py:122,195` | Every slider step writes and syncs the .ini on the GUI thread: measured 2.2 ms median, 4.1 ms max. The cutoff sliders emit on every `valueChanged`, so a drag does ~100 writes/s, up to 40 % of the GUI thread, which also runs the 25 ms DMX tick. | Debounce in `SettingsStore`: queue pending keys and flush with a 300–500 ms single-shot `QTimer`; flush synchronously in `closeEvent`. Keep `set()` for the handlers that save once. | S |
| P6 | Med | Robustness | `src/pylzr/audio/audio_input.py:36-44`; `src/pylzr/engine.py:45`; `src/pylzr/gui/main_window.py:66` | With no usable input device, `AudioInput.__init__` raises, so `MainWindow` never constructs: the app exits with a traceback instead of opening in a "no audio input" state. Tests never see this (fake PyAudio always has a device). | Let `AudioInput` open lazily / catch the open error, start with `_stream = None`, show the audio dot red with the reason, keep the rescan button working. Test with `fail_open = {0}`. | M |
| P7 | Med | Real-time | `src/pylzr/engine.py:168-169` (waveform plot emitted before the FFT is queued), `:172-188` (`spectrum_ready` → plot `setData` runs before the cue logic) | Cue latency includes two GUI-thread round trips plus the plot redraws, because display signals are emitted before the work that matters. A busy GUI (Settings reload, fixtures re-fit, a modal) delays cues by the same amount. | Step 1 (S): in `_process_chunk` queue `_process_audio` first, then emit displays; in `_on_spectrum` run analyzer/sound mode first, emit `spectrum_ready` after. Step 2 is I1. **[gain not measured]** | S |
| P8 | Med | Real-time | `src/pylzr/engine.py:37,68` (unbounded queued connection from the audio thread) | Chunks queue without limit while the GUI is busy, then are processed in a burst, so after a stall sound mode sends a run of stale cues. PortAudio never reports overflow because the callback itself is always serviced. | Keep an in-flight counter (increment in the callback, decrement in `_process_chunk`); when it exceeds 2, skip the display emits and count a "late" diagnostic; analysis still runs in order. Superseded by I1 if that is done. | S |
| P9 | Med | Plan ↔ code | README.md:333-339 (narrative roadmap); D2 plan §12 ("update the roadmap backup"); no PLAN.md/HANDOFF.md in `git ls-files` | The D1–D7 roadmap, the decisions table and the "as built" notes exist only in `~/.claude/plans/*.md`. Every session (and any contributor) re-derives them. | Commit `docs/ROADMAP.md`: phases D3–D7 with scope, the decisions table from the D2 plan, and a short "as built" log. Do it as part of component 12. | S |
| P10 | Low | Real-time | `src/pylzr/gui/main_window.py:209`; `src/pylzr/fixtures/binding.py:265-276` (exhaustive outputs check per reload) | `library.reload()` runs synchronously each time Settings opens: 7 ms today with shipped files only, and it grows with every user binding (each one is fully re-validated). | Cache per file by (path, mtime, size); re-read only changed files. Not urgent; do when a second laser lands. | S |
| P11 | Low | Real-time | `src/pylzr/dmx/discovery.py:136,139-146` | Once the listener is opened the 50 ms drain timer runs for the rest of the app's life, including in MIDI mode. | Start the timer in `search()`/`ping()`, stop it in `_finish_search` when DMX is not active (or let `DMXOutput` own the "watching" state). | S |
| P12 | Low | Hygiene | `pyproject.toml:33-37` (pyqt5-qt5 == 5.15.2 on Windows); runtime shows Qt 5.15.2 | The Windows Qt build is from 2020 and the open-source PyQt5 line gets no further Qt fixes. pyqtgraph, rtmidi and PyAudio are all PyQt6/PySide6-ready. | Plan a PyQt6 spike before D6 (timecode UI): the diff is mostly enum namespaces and `exec_()`; the style sheet and `set_role` approach carry over. | L |
| P13 | Low | Dead code | `renderer.py:67` (`PatternChannel.allows`), `library.py:190` (`source`), `attributes.py:261` (`validate_state`), `renderer.py:153` (`Renderer.defaults`), `app_logger.py:33` (`Tone.NOTICE`) | Used only by tests, never by the app. | Remove, or move the behaviour the tests exercise into a caller. `defaults` and `allows` may earn their keep in D3/component 11; decide then. | S |

## 4. Improvements

| ID | Area | Evidence | Change | Expected benefit | Effort |
|---|---|---|---|---|---|
| I1 | Real-time | `engine.py:60-68` (FFT on a worker, analysis on the GUI thread); `tests/test_engine.py:115-133` asserts GUI-thread processing | Move `AudioAnalyzer` + `SoundMode` into the FFT worker thread ("AnalysisWorker"): audio callback → worker (queued), worker emits display signals and sends cues; `MIDIOutput.press_note` already tolerates another thread (rtmidi send is thread-safe, the note-off `QTimer.singleShot` runs on the worker's event loop). Update the test's contract. | Cues no longer wait for the GUI event loop at all; a frozen GUI cannot stall sound mode. Prerequisite for D4. **[benefit by construction, not measured]** | M |
| I2 | Structure (D3 prep) | `analysis/sound_mode.py:26-31,58-71` (cues are MIDI note ints); `core/protocols.py:4-7`; `dmx/dmx_output.py:183-184` (`press_note` is a no-op) | Introduce `Cue(low_mode, high_mode, dual)` and a `CueOutput` protocol. `SoundMode` and `KeyboardMapper` emit cues; `MIDIOutput` keeps `MODE_MAP` as *its* cue→note table; `DMXOutput` maps cue→scene. | D3 scenes key on cues instead of reverse-mapping note numbers; the golden MIDI test stays byte-identical. | M |
| I3 | Structure (D3 prep) | `gui/main_window.py:54-68,138` (store, library, outputs, engine, discovery owned by the widget) | Extract a non-widget `App`/`Session` that owns the subsystems and wiring; `MainWindow` becomes a view over it. | Headless/CLI mode (the D2 plan already names "command-line tools"), D3 player tests without a window, and a single place for the emergency stop from P1. | M |
| I4 | Structure (D3 prep) | `dmx/dmx_output.py:188-194` (`_tick` sends `universe.frame()`); `fixtures/patch.py:231-244` (`Rig.render` → `{channel: value}`); measured `Rig.render` 0.18 ms | Give `DMXOutput` a `frame_source` callback evaluated inside `_tick` (pull model) and a monotonic frame clock passed to it; scenes render per tick into the base layer, the tester keeps the override layer. | One clock for animation and output, no push/race between scene updates and ticks, and 40 Hz × a few fixtures costs < 1 ms/frame. | M |
| I5 | Structure | `gui/attribute_tester.py` (789 lines): `_PatternCell` at 222-429; three identical wheel guards at 73-95 | Move `_PatternCell` to `gui/pattern_cell.py` (component 11's browser reuses it per the plan); replace the three subclasses with one `wheelEvent` event filter. | Component 11 starts from a reusable widget; the tester file drops to ~550 lines. | S |
| I6 | Structure | `attribute_tester.py:97-110` vs `settings_panel.py:75-99` (two combo fill/select helpers); `settings_panel.py:401,406,412` (three hand-rolled `[:22] + '…'`) vs `widgets.py:223` (`ElidedLabel`) | One `fill_combo`/`select_data` in `widgets.py`; status details as `ElidedLabel`s. | Less duplication in the two most-churned GUI files. | S |
| I7 | Real-time | `core/config.py:1` (`CHUNK = 2048`, 46 ms per update); `analysis/bands.py` | Hop of 1024 with a 2048-sample analysis window (overlap 50 %): keep the FFT size, halve the update period. Regenerate the golden file. | Analysis updates every 23 ms instead of 46 ms; the averaging window at the default rate shrinks from 0.93 s to 0.46 s. Needed by D4's "small changes nudge". **[effect on cue timing not measured]** | M |
| I8 | Hygiene | no bench files tracked (`git ls-files`); the finishing-touches plan referenced a scratchpad `bench_plot.py` | Add `tests/bench_*.py` behind `PYLZR_BENCH=1` with the table above as baselines (render, frame build, FFT, settings save, plot redraw). | Performance regressions show up in review instead of on stage. | S |
| I9 | Hygiene | `gui/spectrum_widget.py:88` sets a global pyqtgraph option inside a widget; `gui/style.py:429` already sets the others | Move `antialias=True` to `style.apply`. | One place for global look settings. | S |
| I10 | Structure | `gui/main_window.py:308,312` (`library.rig()` built twice per `_show_fixtures`) | Build once; folds into I3. | Tidy; trivial cost today. | S |

## 5. Plan changes

Against the D2 plan (`analyze-the-repo-and-smooth-quasar.md`) and its continuation (`recall-the-big-implementation-clever-wren.md`):

1. **Insert "D2.5: fail-safe output" before component 11.** Scope: P1, P2, P3, P4, P6, P8, plus an acceptance test set:
   exception in a slot → blackout sent; GUI stalled 2 s → frames resume and no stale cue burst; audio stops → warning,
   dot red, quiet cue. Reason: scenes (D3) are the first phase where the laser runs unattended; today every abnormal exit
   leaves it on its last look.
2. **Component 11 (Patterns tab):** do I5 first and list `gui/pattern_cell.py` under "Reuse". Add to its hardware check:
   confirm the CR011R's behaviour on DMX loss (hold vs. blackout) and note it in the README's DMX section.
3. **Component 12 (docs + v0.6.0):** add P9 (`docs/ROADMAP.md`) alongside `docs/fixtures.md`. The README's "Creator's
   Commentary" roadmap paragraph should point at it.
4. **Add "D3 prep" as the first D3 components:** I2 (cues), I3 (app object), I4 (pull-model frame clock), in that order.
   Each is a no-behaviour-change refactor with the golden MIDI and DMX tests as the guard.
5. **D4 (dynamic sound mode):** make I1 and I7 its first two components. Its "small changes nudge" needs per-chunk
   features at a steady period that the GUI cannot disturb.
6. **Reorder the later phases to D3 → D4 → D6 → D5.** D5 (auto-binding standard OFL lasers, fallbacks, coverage report)
   has no user until a second laser exists; D6 (timecoded shows) and D7 (ML) build directly on D3/D4 content. Pull D5
   forward only when a second fixture is bought.
7. **Cut the C++ rewrite from the roadmap** (README.md:341-343). The measured hot paths are 1–180 µs; latency is set by
   the 46 ms chunk, the averaging window and GUI-thread coupling, which I1/I7 fix in Python.
8. **Add a PyQt6 spike before D6** (P12). Timecode UI work will be the largest new GUI surface; build it on the
   supported toolkit.
9. **Keep** the override-layer-only tester rule, the pure `fixtures` package and the exhaustive safety checks; they are
   the strongest parts of the design.

## 6. Order of attack

1. **P2** — reorder `closeEvent`: smallest change, closes the most common "laser stays on" path.
2. **P3** — repeat the blackout frame: one-line loop, removes the lost-packet case.
3. **P1** — excepthook + emergency stop: covers every bug not yet found.
4. **P5** — debounce settings writes: the one measured GUI-thread cost that scales with user action.
5. **P7** — reorder emits in the engine: free latency, no structural change.
6. **P4** — detect audio stall: stops a silent failure from holding a cue.
7. **P6** — start without an input device: first-run and venue robustness.
8. **P8** — bound the chunk queue (skip if I1 follows soon).
9. **I5** — split out `_PatternCell` before component 11 builds on it.
10. **P9** — commit the roadmap with component 12.
11. **I2** — cue abstraction, first D3 prep.
12. **I3** — app object, second D3 prep (also hosts the emergency stop).
13. **I4** — pull-model frame clock, last D3 prep.
14. **I1** — analysis worker thread, first D4 step.
15. **I7** — hop/overlap, second D4 step (regenerates the golden file).
16. **I8** — benchmarks, so 14–15 are measured not assumed.
17. **I6**, **I9**, **I10** — small tidy-ups, batch into any GUI commit.
18. **P13** — dead code, decide after component 11.
19. **P10**, **P11** — low-cost polish when touching those files.
20. **P12** — PyQt6 spike before D6.
