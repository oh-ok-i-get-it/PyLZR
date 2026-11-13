# PLAN: D2.5 fail-safe output (audit P2, P3, P1, P5, P7, P4, P6)

Branch: `hayden/components-pt3`. Same procedure as D2: one task at a time, stop for review, commit message given.
Design: `docs/design/safety-phase.md`. Every task ends with `pytest -q` (1318 tests before Task 3, 1391 after Task 5),
`ruff check .`, and the golden files unchanged (`tests/golden/pipeline.json`, `tests/golden/gruolin_renders.json`).
Tasks 6 and 7 (P4, P6) were added on 13 Nov 2026, when the audit's deferred items were decided (`docs/AUDIT.md`).

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

## Task 4 — Debounced settings writes (P5) [careful] — DONE

**Files:** `src/pylzr/gui/settings_store.py:1-91`; `src/pylzr/gui/main_window.py:46-48` (docstring) and
`closeEvent` `:423-436` (flush right after `_close_dmx_tester()`, before `engine.shutdown()`);
`tests/test_settings_store.py:77-81` (replace), new tests there and in `tests/test_safety.py`. Implementation plan:
`docs/plans/task-4-debounced-settings.md`.

**Change:** `SettingsStore.set()` writes the value into `QSettings` but defers `sync()` to a single-shot `QTimer`
(`FLUSH_MS = 400`, restarted on every set). Qt's own automatic write is held back too: plain `QSettings` posts itself
an `UpdateRequest` after any change and writes on the next event-loop pass, so the store uses a `QSettings` subclass
that ignores that event (Q14). `flush()` syncs now and stops the timer. `clear()` stops the timer, clears and syncs.
The timer needs a `QCoreApplication`; without one (plain unit tests) `set()` syncs immediately, so the store works
headless. A failed write (`sync()` doesn't raise; `status()` reports it) is logged once per store. `closeEvent`
flushes after the blackout and before anything that can block.

**Acceptance:**
- 100 `set()` calls in a row, with events processed between them, produce no write until `flush()`, then one (count
  `sync` calls through a monkeypatch, and read the file text).
- With nothing else called, the value is on disk once the timer fires (`wait_until` on the file text; tests patch
  `FLUSH_MS` to a few ms).
- `flush()` writes immediately. A window closed right after a change has it **in the file on disk** when `closeEvent`
  returns, read before any other store is created (a new `SettingsStore` or `QSettings` would itself write pending
  changes, and stores in one process share Qt's cache, so a same-process restart test can't show this). The flush
  comes after the blackout and before `engine.shutdown()`.
- Ctrl+C right after a change keeps it (written by `closeEvent`, not the timer).
- `test_each_change_is_written_to_disk_immediately` becomes "written when the timer fires, and at once on flush";
  "immediately" stays true without a `QCoreApplication`.
- Reset to defaults still clears the file (`test_clear`, `test_reset_to_defaults`), and drops a pending write.
- The new tests add well under 0.5 s to the suite.

**Verify:** `pytest tests/test_settings_store.py -q`; full suite; manual: drag a cutoff slider for 5 s and check the
.ini changed once, about 0.4 s after release, not hundreds of times (watch its mtime).

---

## Task 5 — Cue logic before display redraws (P7) [mechanical] — DONE

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

## Task 6 — Notice an audio stall (P4) [careful]

**Files:** new `src/pylzr/audio/stall.py`, `src/pylzr/audio/__init__.py`; `src/pylzr/engine.py` (constants after
`:17`, signal after `:37`, `__init__` `:42-73`, `start`/`stop` `:77-84`, `set_sound_mode` `:118-130`,
`switch_device`/`refresh_devices` `:136-153`, new methods after `:201`); `src/pylzr/analysis/sound_mode.py` (new
`go_quiet` after `:84`, `update_mode` `:70`); `src/pylzr/analysis/analyzer.py:21-37` (`_reset` → `reset`);
`src/pylzr/midi/midi_output.py` (`__init__` `:57`, new `last_note`/`forget_last_note`, `close` `:95-103`,
`press_note` `:105-119`, `panic` `:121-153`); `src/pylzr/core/protocols.py:7`, `src/pylzr/core/output_switch.py:39-40`,
`src/pylzr/dmx/dmx_output.py:296` (`skip_if_last` keyword); `src/pylzr/gui/main_window.py` (one connection after
`:125`, `_on_control_mode_changed` `:283-284`); `tests/conftest.py` (autouse fixture); `tests/helpers.py`
(`FakeClock`, `watch_with`, `stall`); new `tests/test_stall.py`; new tests in `tests/test_sound_mode.py`,
`tests/test_analyzer.py`, `tests/test_midi_output.py`, `tests/test_output_switch.py`, `tests/test_engine.py`,
`tests/test_main_window.py`, `tests/test_main_window_dmx.py`, `tests/test_safety.py`; `README.md:288`.
Implementation plan: `docs/plans/task-6-audio-stall.md`.

**Change:** PortAudio's callback stamps a `StallWatch` before queueing each chunk. A 250 ms timer on the GUI thread
asks it whether audio has stopped: no chunk for `STALL_TIMEOUT_S = 2.0` while the engine is started (Q16). On a stall
(once): with sound mode on, `SoundMode.go_quiet()` sends the quiet cue (LOW 0 / HIGH 0, SPACE) unless the mode is
already quiet; the analyzer's partial window and the last averages are dropped; one WARNING in the console that says
what happened and what to do (`Audio: no sound from "<device>" for 2 s: the input has stopped (unplugged, or its
driver stopped). Check the audio interface and its cable, then click ↻ next to Device in Settings (⚙).`);
`audio_status_changed(False, 'No audio')` turns the Settings dot red. On the first chunk after it: one INFO
(`"<device>" is sending sound again.`), dot green with the device name. A check that comes over 2 s late (sleep, a
blocked GUI thread) restarts the wait instead. Starting capture, switching device and rescanning restart it too. Not
the emergency stop, and DMX output is untouched (Q15). No automatic reopen (Q17, for now).
SPACE stays consistent with Task 3's Q10–Q12 (ASSUMPTION(Q21)): sound mode's quiet cue already is SPACE, and the
stall uses that path; `MIDIOutput` now records the last Note ON, and neither sound mode's SPACE cue
(`press_note(…, skip_if_last=True)`) nor the emergency stop's SPACE (`panic`) goes out when SPACE is already the last
note sent. Checked and sent under the MIDI send lock. Switching Control Mode to MIDI forgets the last note when it
re-arms SPACE; opening a port starts with none. The keyboard's SPACE key never skips.

**Acceptance:**
- No chunk for 2 s with sound mode on: exactly one quiet cue (note 106), one WARNING, `audio_status_changed(False,
  'No audio')`, `modes_updated` with LOW 0 / HIGH 0. Already quiet: no cue. Sound mode off: no cue, still warned.
- Still no audio on later checks: nothing more is sent or logged.
- Audio back: one INFO, `audio_status_changed(True, <device>)`; the next full window sends its cue.
- The warning and the recovery line appear in the window's console at its default level (Info), the warning with
  its icon, and name the device, the cause and the ↻ button.
- Turning sound mode on during a stall sends the quiet cue, not the cue from before the stall.
- A busy GUI thread (chunks queued, not yet processed) is not a stall; a late check is not a stall.
- SPACE reaches SoundSwitch once for: a stall then an emergency stop (and a second stop right after); an emergency
  stop then a stall; two stalls with quiet audio between; sound mode toggled during a stall. Two stalls with a lit
  cue between send SPACE after each lit cue, never twice in a row. A skipped SPACE leaves the arm set (Q11).
  `panic()` and a skipping `press_note` on two threads at once send SPACE once (deterministic test).
- Task 3's SPACE tests pass unchanged (re-enabling MIDI or opening a port still gives the next stop its SPACE).
- DMX: during a stall in DMX mode the frames sent are unchanged (tester values still out, no blackout).
- Every other test runs with stalls off (autouse fixture); the golden pipeline test is unchanged.

**Verify:** `pytest tests/test_stall.py tests/test_sound_mode.py tests/test_analyzer.py tests/test_midi_output.py
tests/test_output_switch.py tests/test_engine.py tests/test_main_window.py tests/test_main_window_dmx.py
tests/test_safety.py -q`; the real-timer and two-thread tests 20× each; full suite ×3 (1428); `ruff check .`.
Manual (you): unplug the USB microphone with sound mode on, watch the in-app console, the Settings dot and
SoundSwitch; plug it back and press ↻; trigger an emergency stop during a stall and check a MIDI monitor shows one
SPACE.

---

## Task 7 — Start without an input device (P6) [careful]

**Files:** `src/pylzr/audio/audio_input.py:29-44` (`__init__`), `:92-126` (`start`, `stop`, `switch_device`,
`refresh_devices`), `:146-150` (`close`); `src/pylzr/engine.py` (skip the stall check with no stream);
`src/pylzr/gui/main_window.py:113`, `:194-195`, `:246-262` (`_show_audio_device` and its callers);
`src/pylzr/gui/settings_panel.py` (`set_audio_devices` with an empty list); `tests/fakes/pyaudio.py` (no default
device when there are no inputs, as PortAudio does); tests in `tests/test_audio_input.py`
(`test_failed_open_releases_portaudio` changes), `tests/test_engine.py`, `tests/test_main_window.py`.
Implementation plan: written after Task 6 is reviewed (`docs/plans/task-7-no-input-device.md`).

**Change:** `AudioInput.__init__` no longer raises when no input can be opened (no device, device busy, PortAudio
fails to start): it logs a WARNING with the reason, keeps `_stream = None`, `device_name = None`, `error = <reason>`.
`start()`/`stop()` record whether capture is wanted; `switch_device()` and `refresh_devices()` work from that state
and start the new stream if capture is wanted. The engine skips the stall check while no stream is open. The window
shows "No input device" (dot red) and an empty device list; keyboard cues, MIDI, DMX and the tester all work. No
automatic retry (design Q20): ↻ opens a device plugged in later.

**Acceptance:**
- With no input devices (fake), the window opens, the dot is red with "No input device", one WARNING names the
  reason, and a keyboard cue reaches MIDI.
- `fail_open = {0}` (the default is busy): same, with the error in the WARNING.
- A device added, then ↻: it opens and captures (`harness.feed` produces frames), dot green.
- Choosing a device from the no-input state opens and captures it.
- No stall warning while there's no stream; a stall is still detected once a stream is open.
- Closing the window from the no-input state releases PortAudio and the FFT thread.
- The saved `audio/device` isn't overwritten by a start with no device.

**Verify:** `pytest tests/test_audio_input.py tests/test_engine.py tests/test_main_window.py -q`; full suite ×3;
`ruff check .`. Manual (you): start PyLZR with every input disabled in the OS sound settings; then enable one and ↻.

---

## After task 7
- Hardware check (you): close PyLZR while the Gruolin is lit; pull the node's cable, then plug it back; note what the
  CR011R does without DMX (hold or dark) and record it in the README's DMX section.
- Then the D2 remainder (components 11, starting with I5, and 12), then the D3 prep refactors, in the order in
  `ROADMAP.md`.
