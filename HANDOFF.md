# Handoff

## Current state

Branch `hayden/components-pt3`. Task 3 is committed (`efa64b9`, follow-up `c5a2601`) and Task 4 as `37c8dc0`. Task 5
(cue logic before display redraws, P7) is **implemented, not committed**; marked DONE in PLAN.md. This was the last task
in PLAN.md.

What changed (Task 5):
- `engine.py` `_process_chunk`: gain, then `_process_audio.emit` (queues the FFT), then level, then `waveform_ready`.
- `engine.py` `_on_spectrum`: count the frame, split, push, sound mode, `averages_ready` / `modes_updated`, and
  `spectrum_ready` last. No values change.
- `tests/test_engine.py`: `test_cue_logic_runs_before_display_redraws` (DirectConnection recorders; 20 chunks = one
  window; per chunk `_process_audio < waveform_ready`; `modes_updated` before the window's last `spectrum_ready`).

Results (Task 5):
- `pytest -q`: 1391 passed, three runs in a row (11.64 s, 11.60 s, 11.60 s). `ruff check .`: clean. `tests/golden/`
  unchanged (`git status` shows only engine.py, test_engine.py, PLAN.md and this file). `test_pipeline_golden.py` passes
  unchanged.
- With the old `engine.py` restored (from `HEAD`), the new test fails (the other 18 engine tests pass); the fix was put
  back afterwards.
- No manual checks: the plan lists none for this task.

Results (Task 4):
- `pytest -q`: 1390 passed, three runs in a row (11.55 s, 11.86 s, 11.61 s; baseline 11.57 s). `ruff check .`: clean.
  `tests/golden/` unchanged.
- Added suite time: the 12 new tests run in 0.42 s together (`--durations=0`; slowest: the close-order window test,
  0.05 s). Under the 0.5 s target.
- Timing tests (`-k` list from the plan, 8 tests) passed 20 runs out of 20.
- Regression checks, each restored afterwards (the full suite passes again, `git diff` shows only the task's work):
  `event()` passing everything fails #1, #2, #3; `set()` calling `_sync()` fails #1, #2, #5, #7, #10; timeout not
  connected fails #3, #12; no restart fails #5; no flush in `closeEvent` fails #10, #11; flush after
  `engine.shutdown()` fails #10; flush before `dmx_out.stop()` fails #10; `clear()` without the timer stop fails #7.
  Every guard caught its regression (a few also caught extra tests, which the plan allows).
- The manual checks in plan section 8 (1-3) were **not run** (they start the app; the laser/MIDI/DMX paths are not
  safe to drive from here). Only the tests ran.

Results (Task 3):
- `pytest -q`: 1379 passed (1373 after `efa64b9`), three runs in a row. `ruff check .`: clean. `tests/golden/`
  unchanged.
- Race and ordering tests (`-k "dark or show_frame or in_flight or being_sent or two_stops"`): 20 runs in a row, all
  passed.
- Each fix was removed in turn and its test failed 5 runs out of 5: the DMX send lock, the SPACE lock, the flag
  check, the second blackout, the panic ids in `start()`, `_may_be_lit`, the re-arm order and the port re-arm. Every
  file was restored byte for byte.
- The manual checks in plan section 8 (1-5) were **not run**: they start the app, drive DMX/MIDI to real ports, or
  need the laser. Only the fake-socket / fake-rtmidi tests ran.

## Next task

PLAN.md is finished once Task 5 is reviewed and committed. Per "After task 5": (1) hardware check (you): close PyLZR
while the Gruolin is lit; pull the node's cable, then plug it back; note what the CR011R does without DMX (hold or
dark) and record it in the README's DMX section. (2) Then the D2 remainder (components 11 and 12), then the D3 prep
refactors, in the order in `ROADMAP.md`.

## Assumptions and deviations to confirm

1. **ASSUMPTION(Q11)** (from the plan): SPACE's arm is used up only when SPACE actually reaches the MIDI port. A stop
   with no open port, or a failed Note ON, leaves it armed. One line in `MainWindow._midi_emergency_stop`.
2. `__main__.py`: the plan's snippet left out the `if __name__ == '__main__': main()` block. I kept it, since
   `python -m pylzr` needs it.
3. Plan test 7.4 #7 (`test_panic_never_raises`): the autouse `_no_real_network` fixture sets monkeypatch up first, so
   it is torn down after the `out` fixture's `close()`. The test undoes its patch with `monkeypatch.context()`; the
   section comment in `tests/test_dmx_output.py` now says so.
4. Plan tests 22 and 23 (FFT thread): replacing `FFTWorker.process` with a `pyqtSlot` wrapper never gets called
   (PyQt registered the original as the slot). The tests make the first `np.fft.rfft` call on a non-main thread raise
   instead, which raises inside the real `process` on the FFT thread. Behaviour under test is the same.
5. Test 7.5 #34 patches the global `atexit.register` for the length of one test; `monkeypatch` restores it.
6. The deterministic SPACE test (7.5 #28) swaps the window's class for a subclass with a `_space_armed` property, to
   pause the first stop between reading and clearing the arm. It's the only way to stop a thread inside that
   one-statement test-and-clear without changing the production code for the test.
7. Source and test files keep CRLF endings in the working tree; git normalises them (autocrlf).
8. Task 4: `get_logger` is imported as `from ..core.app_logger import get_logger`, placed after the `..core` import
   block as the plan says (alphabetical before `..dmx`). Nothing else differed from the plan.
9. Task 4, test #10 (`test_closing_right_after_a_change_writes_it_after_the_blackout`) counts all-zero DMX frames
   seen when `flush` runs, as the plan says. Moving the flush before `dmx_out.stop()` does fail it, so the count
   does discriminate in practice.
10. **Task 5, deviation to confirm:** the plan says to emit `spectrum_ready` last, but `_on_spectrum` returned early on
    the frames that don't complete an averaging window. Moving the emit to the end of the old shape would have dropped
    `spectrum_ready` on most frames (19 of 20 at the default count rate). I replaced the early return with an
    `if result is not None:` block so `spectrum_ready` still fires on every frame, after the cue. Emitted frames and
    values are unchanged (the golden test confirms).
11. Task 5: the ordering test pairs `modes_updated` with the window's last `spectrum_ready`, since `modes_updated` only
    fires once per window; the plan's "for each frame" holds for the frames that produce a cue.
