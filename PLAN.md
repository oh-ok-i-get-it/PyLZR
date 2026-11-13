# PLAN: D2.5 fail-safe output (audit P2, P3, P1, P5, P7)

Branch: `hayden/components-pt3`. Same procedure as D2: one task at a time, stop for review, commit message given.
Design: `docs/design/safety-phase.md`. Every task ends with `pytest -q` (1318 tests before Task 3), `ruff check .`, and the
golden files unchanged (`tests/golden/pipeline.json`, `tests/golden/gruolin_renders.json`).

Tags: **[mechanical]** = the change is fully specified here; **[careful]** = judgement calls, read the design first.

---

## Task 1 — Blackout before anything that can block on exit (P2) [mechanical] — DONE

**Files:** `src/pylzr/gui/main_window.py:371-378` (`closeEvent`), `src/pylzr/engine.py:84-92` (`shutdown`).

**Change:** in `closeEvent`, call `self.dmx_out.stop()` first (sends the blackout while the socket is open), then
`_close_dmx_tester()`, `engine.shutdown()`, `discovery.close()`, `midi_out.close()`, and `self.dmx_out.close()` last.
In `AudioEngine.shutdown`, `self.fft_thread.wait(2000)` and log a warning if it returns False.

**Acceptance:**
- In DMX mode, the first thing closing the app does is send dark frames; the audio stream is closed after them.
- `tests/test_main_window_dmx.py::test_closing_the_app_blacks_out_and_releases_the_socket` still passes.
- New test: monkeypatch `AudioInput.close` to record how many dark frames were already in `fake_udp.sent`; assert ≥ 1.
- New test: an FFT thread that never finishes (monkeypatch `wait` to return False) still lets `closeEvent` complete.

**Verify:** `pytest tests/test_main_window_dmx.py tests/test_engine.py -q`, then the full suite.

---

## Task 2 — Repeat the blackout (P3) [mechanical] — DONE

**Files:** `src/pylzr/dmx/dmx_output.py:16` (constant), `:133-134` (`configure`), `:156-163` (`stop`);
tests `tests/test_dmx_output.py:70-79, 90-94, 126-136`, `tests/test_main_window_dmx.py:77-89, 174-181`.

**Change:** add `BLACKOUT_REPEATS = 3` next to `_BLACKOUT`. `stop()` sends `_BLACKOUT` that many times; `configure()`
does the same to the old node while active. Sequence numbers keep advancing (`_send` already does).

**Acceptance:**
- `stop()` after `start()` yields exactly 1 + 3 packets, the last 3 all `bytes(512)`.
- `close()` after `start()` yields 1 + 3 packets; a second `close()` sends nothing.
- `configure()` while sending: the old node's last 3 packets are dark; the new node's first packet carries the show.
- Stopped output still never sends (`test_stopped_output_never_sends`).
- Update the counts in the tests listed above; the window-level tests assert `frames()[-3:] == [bytes(512)] * 3`.

**Verify:** `pytest tests/test_dmx_output.py tests/test_main_window_dmx.py -q`.

---

## Task 3 — Exception hook and emergency stop (P1) [careful] — DONE

**Files:** new `src/pylzr/core/safety.py`; `src/pylzr/__main__.py:1-14`; `src/pylzr/dmx/dmx_output.py` (`panic()`,
send lock and flag in `_send()` `:213-217`, panic ids in `start()` `:152-161` and `stop()`); `src/pylzr/midi/midi_output.py`
(`panic(note)`, send lock); `src/pylzr/midi/key_map.py` + `midi/__init__.py` (`BLACKOUT_NOTE`);
`src/pylzr/gui/main_window.py` (`:12` import, `:44` signature, registration after `:65`, re-arm in
`_on_control_mode_changed` `:261-272`, new methods before `:352`, every `midi_out.open` through
`_open_midi_port`, unregister in `closeEvent` `:371-382`);
`tests/conftest.py:101-111`; new `tests/test_safety.py`; new tests in `tests/test_dmx_output.py`,
`tests/test_midi_output.py`, `tests/test_key_map.py`. Implementation plan: `docs/plans/task-3-emergency-stop.md`.

**Change (see the design, "Interfaces"):** `EmergencyStop` holds stop callables. `install_excepthook()` sets
`sys.excepthook` and `threading.excepthook` to a handler that first calls `EmergencyStop.trigger()`, then logs the
traceback at ERROR (a repeating error: once, then one line at the 2nd, 4th, 8th… time, Q7), then, after the first
error only, follows design Q1: the app keeps running with DMX output stopped and the Control Mode dropdown untouched;
the user re-enables DMX by switching Control Mode. A `KeyboardInterrupt` (Ctrl+C) triggers the stop, then quits
through the normal close path (Q8). `DMXOutput.panic()` first takes a new panic id, which makes `_send()` refuse every
non-dark frame until a `start()` that comes after a `stop()` (checked under a short send lock, so no show frame can
follow the blackout; a `start()` racing with the panic doesn't end it). If the output may be lit (`_may_be_lit`, set
before start()'s first frame), it then sends `BLACKOUT_REPEATS` dark frames straight through the sender, swallowing
every exception; if the lock took over 5 ms it sends them without it, then again once the send holding it is done.
It asks the GUI thread to stop the timer through a queued signal (`stop()` blacks out once more). `main()` sets up console logging first,
then installs the hook and the `atexit` stop before any Qt object exists. The window registers `dmx_out.panic` as
`'dmx'` and a second stop, `'midi'` (Q2). In MIDI mode it sends MIDI all-notes-off, and on the first stop after MIDI
was (re)enabled also the SPACE note (106, on and off), so SoundSwitch goes to its blackout look. Later stops send
all-notes-off only; switching Control Mode to MIDI (re-armed before the switch) or opening a MIDI port re-arms SPACE
(Q10, Q12). In DMX mode it sends nothing.
`MIDIOutput.panic()` never raises and sends nothing while no MIDI port is open.

**Acceptance:**
- A `RuntimeError` raised inside a slot (e.g. a test-only slot connected to a signal, emitted from the GUI thread)
  does not abort the process; the log shows the traceback once; 3 dark frames are sent before the hook returns; after
  the next event-loop pass `dmx_out.active` is False and the last 3 frames are dark.
- The same from the FFT thread (raise in a monkeypatched `FFTWorker.process`) while the DMX timer is running, with the
  FFT thread's sends slowed down: no non-dark frame follows the first dark frame.
- In MIDI mode (DMX off): no DMX is sent; the SPACE note and all-notes-off are sent (all-notes-off first, then SPACE
  on and off); and the app keeps running. With no MIDI port open, nothing is sent and the app keeps running.
- A second stop in MIDI mode sends all-notes-off only; after switching Control Mode to MIDI again, or opening a MIDI
  port, the next stop sends SPACE again. Two stops at once on two threads send SPACE once (deterministic test: fails
  without the arm's lock).
- The send lock and the second blackout after a send stuck past 5 ms each have a deterministic test that fails
  without them; a `start()` before the panic's own `stop()` sends nothing lit; a panic right after start()'s first
  frame blacks out.
- In DMX mode the emergency stop sends no MIDI.
- After the stop the Control Mode dropdown is unchanged; switching Control Mode to MIDI and back to DMX sends DMX again.
- Ctrl+C (a `KeyboardInterrupt` in a slot) triggers the stop, then the window closes through `closeEvent` (engine shut
  down, sockets released, last 3 frames dark).
- `trigger()` twice sends dark frames once per call but never raises, even if a stop callable raises.
- `atexit` runs the stop too, also after the Qt object is deleted (test: subprocess that registers, sets a fake
  sender, exits via `sys.exit`).

**Verify:** `pytest tests/test_safety.py tests/test_dmx_output.py tests/test_midi_output.py -q`; the race tests 20×
in a row; full suite (1379 after the review follow-up, plan §10); manual: run the app, inject `raise` in a handler,
watch the console and the DMX indicator; Ctrl+C in the terminal; MIDI mode with a MIDI monitor.

---

## Task 4 — Debounced settings writes (P5) [careful]

**Files:** `src/pylzr/gui/settings_store.py:83-87`; `src/pylzr/gui/main_window.py:371-378` (flush in `closeEvent`,
before `dmx_out.close()`); `tests/test_settings_store.py:77-81` (rewrite), new tests there.

**Change:** `SettingsStore.set()` writes the value into `QSettings` but defers `sync()` to a single-shot `QTimer`
(`FLUSH_MS = 400`, restarted on every set). `flush()` syncs now and stops the timer. `clear()` flushes. The timer
needs a `QCoreApplication`; without one (plain unit tests) `set()` syncs immediately, so the store works headless.

**Acceptance:**
- 100 `set()` calls in a row produce one write (count `sync` calls through a monkeypatch, or file mtime/size).
- A value is on disk within `FLUSH_MS` + 100 ms without any other call (`wait_until` on the file text).
- `flush()` writes immediately; `closeEvent` leaves nothing pending (restart test `test_settings_restored_after_restart`
  still passes, and a variant that closes within 50 ms of the last change still restores it).
- `test_each_change_is_written_to_disk_immediately` becomes "written within the debounce, and at once on flush".
- Reset to defaults still clears the file (`test_clear`, `test_reset_to_defaults`).

**Verify:** `pytest tests/test_settings_store.py -q`; full suite; manual: drag a cutoff slider for 5 s and check the
.ini changed once or twice, not hundreds of times (watch its mtime).

---

## Task 5 — Cue logic before display redraws (P7) [mechanical]

**Files:** `src/pylzr/engine.py:154-169` (`_process_chunk`), `:171-188` (`_on_spectrum`); new test in
`tests/test_engine.py`.

**Change:** in `_process_chunk`: gain, then `self._process_audio.emit(chunk)` (queues the FFT), then level, then
`waveform_ready`. In `_on_spectrum`: count the frame, split, push, run sound mode and emit `averages_ready` /
`modes_updated`, and emit `spectrum_ready` last. No values change.

**Acceptance:**
- New test: connect `DirectConnection` recorders to `_process_audio`, `waveform_ready`, `modes_updated` and
  `spectrum_ready`; feed one window; assert the order `_process_audio < waveform_ready` and
  `modes_updated < spectrum_ready` for each frame.
- `tests/test_pipeline_golden.py` passes unchanged (same frames, averages and notes).
- `tests/helpers.py:119-125` (the harness records `spectrum_ready` and `averages_ready`) needs no change.

**Verify:** `pytest tests/test_engine.py tests/test_pipeline_golden.py -q`; full suite.

---

## After task 5
- Hardware check (you): close PyLZR while the Gruolin is lit; pull the node's cable, then plug it back; note what the
  CR011R does without DMX (hold or dark) and record it in the README's DMX section.
- Then the D2 remainder (components 11 and 12), then the D3 prep refactors, in the order in `ROADMAP.md`.
