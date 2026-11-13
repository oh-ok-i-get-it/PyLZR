# Design: D2.5 fail-safe output

## Scope
Make every abnormal exit, and every ordinary one, leave the laser dark, and keep the GUI thread's own work from
delaying DMX frames. Covers audit P2 (shutdown order), P3 (repeated blackout), P1 (exception hook + emergency stop),
P5 (debounced settings writes) and P7 (cue logic before redraws). Out of scope: audio-stall detection (P4), starting
without an input device (P6), bounding the chunk queue (P8), moving analysis off the GUI thread (D4), and anything the
node does on its own when DMX stops (a hardware setting, checked by hand).

## Interfaces
```python
# src/pylzr/core/safety.py  (pure Python, no Qt)
class EmergencyStop:
    def register(self, name: str, stop: Callable[[], None]) -> None   # idempotent per name
    def unregister(self, name: str) -> None
    def trigger(self, reason: str) -> None     # runs every stop once, in registration order, then logs a summary;
                                              # a stop that raises is logged and the rest still run; never raises;
                                              # a trigger from inside a stop (same thread) returns at once
    @property
    def triggered(self) -> bool

def install_excepthook(stop: EmergencyStop, on_handled: Callable[[], None] | None = None,
                       on_interrupt: Callable[[], None] | None = None) -> None
    # sets sys.excepthook and threading.excepthook; the handler calls stop.trigger('unhandled exception') first, then
    # logs the traceback (ERROR, logger 'pylzr.safety'; a repeating error once, then one line at the 2nd, 4th, 8th…
    # time: Q7), then on_handled() after the first error only (Q1). A KeyboardInterrupt: stop.trigger('interrupted'),
    # one WARNING line, then on_interrupt() (Q8: main() queues QApplication.closeAllWindows). Never raises.

# src/pylzr/dmx/dmx_output.py
BLACKOUT_REPEATS = 3
def stop(self) -> None          # as today, but sends BLACKOUT_REPEATS dark frames before setting status 'off'
def configure(...) -> bool      # the old node gets BLACKOUT_REPEATS dark frames while active
def panic(self) -> None         # from any thread: first take a new panic id (from then on _send() refuses every
                                # non-dark frame, until a start() that comes after a stop()); if the output may be lit
                                # (_may_be_lit: set before start()'s first frame), send BLACKOUT_REPEATS dark frames
                                # through the sender under the send lock (if that takes over 5 ms: without it, then
                                # again once the send holding it is done); then emit _stop_requested (queued) so the
                                # GUI thread runs stop(); swallow every error

# src/pylzr/midi/midi_output.py
def panic(self, note: int | None = None) -> bool   # from any thread: all-notes-off (CC 123, channel 1), then `note`
                                                   # ON and OFF at once; nothing while no port is open; never raises;
                                                   # True if the note's ON was sent
# src/pylzr/midi/key_map.py
BLACKOUT_NOTE = 106             # SPACE; SoundSwitch's blackout look

# src/pylzr/gui/settings_store.py
FLUSH_MS = 400
def set(self, key, value) -> None   # stores the value, (re)starts the flush timer; syncs at once with no QCoreApplication
def flush(self) -> None             # sync now, stop the timer
def clear(self) -> None             # flushes

# src/pylzr/engine.py  (order only; no new names)
```
Ownership: `main()` sets up console logging, creates the `EmergencyStop`, installs the hook and registers
`atexit.register(stop.trigger, 'exit')`, all before any Qt object exists, then passes it to `MainWindow(safety=…)`.
`MainWindow` registers `dmx_out.panic` under the name `'dmx'`, then `'midi'` (in MIDI mode: all-notes-off, plus SPACE
once per MIDI enable or MIDI port opened, Q10, Q12), and owns the SPACE arm. Later the app object does this, see `app-object.md`. The store
owns its timer. `DMXOutput` owns the blackout policy.

## Threading / timing
- `sys.excepthook` runs on the thread that raised. PyQt5 wraps every slot call: with a custom hook installed it is
  called instead of `qFatal()`, on the GUI thread for GUI slots and on the FFT thread for `FFTWorker.process`.
  `threading.excepthook` covers plain threads (PortAudio's callback thread is not a Python thread; an exception there is
  swallowed by PyAudio and must not be relied on).
- `panic()` may run on any thread. Before its sends it reads only Python state (`_closed`, `_may_be_lit`): at exit the
  Qt objects may already be deleted. It takes a new panic id (so `_panicked`), sends under `DMXOutput`'s send lock,
  and emits a queued signal (guarded: the Qt object may be gone). `stop()` records the latest panic it has run after
  and `start()` resumes only up to that one, so a `start()` racing with a `panic()` can neither lose it nor end it
  before its own `stop()` has run; each of these fields has one writer. `QTimer.stop()` happens on the GUI thread via that signal. If the GUI thread
  is the one that raised, the queued stop runs on the next event-loop pass, after the handler returns.
- No show frame after the blackout: `_send()` checks `_panicked` and sends under the same lock, so the check and the
  send are one step relative to `panic()`. A flag alone isn't enough: the GUI thread could read it, lose the GIL, and
  send its show frame after the dark ones. The lock is held only for the check, one packet build and one non-blocking
  `sendto` (three for `panic()`): microseconds, well inside the 25 ms frame. No Qt call, signal or logging happens
  under it, so nothing can re-enter it. `panic()` waits at most 5 ms for it, then sends anyway. That only happens if
  the GUI thread was descheduled mid-send, and its show frame then goes out after those dark frames, so `panic()`
  then waits up to 0.1 s for that send to finish and blacks out again: the last frame is dark. With every send under
  this lock, sequence numbers stay unique and `UdpSender`'s `last_error`/`dropped` have one writer at a time.
- MIDI: `MIDIOutput` serialises `press_note`, the delayed Note OFF, `close()` and `panic()` with its own lock (rtmidi
  doesn't promise thread safety); `panic()` waits at most 0.1 s for it. The SPACE arm is a test-and-clear under a
  small lock in the window, so two stops at once send SPACE once. Switching Control Mode to MIDI re-arms it before
  the output switches, so a stop in between either still sees DMX or finds it armed.
- `KeyboardInterrupt` is raised on the main thread only; `on_interrupt` queues the close there (`QTimer.singleShot`),
  so `closeEvent` never runs inside the hook.
- Deadline: dark frames leave within one tick (25 ms) of the trigger. The stop runs before any logging. The three sends
  are back to back (microseconds); spacing them over ticks would need the timer that may be the thing that failed.
- Settings: `set()` on the GUI thread; the flush timer fires on the GUI thread; one `sync()` costs 2–4 ms measured,
  so at most one such stall per `FLUSH_MS` of user input instead of one per slider step.
- Engine order: `_process_chunk` queues the FFT before drawing the waveform; `_on_spectrum` runs the analyzer, sound
  mode and cue before emitting `spectrum_ready` (plot redraw). Same thread, same values, less time before the cue.

## Failure modes
| Failure | Today | After this phase |
|---|---|---|
| Exception in a GUI slot | process aborts, node holds last look | 3 dark frames at once, then only dark frames; `stop()` on the next event-loop pass (3 more); traceback logged once; then Q1 |
| Exception in `FFTWorker.process` | same abort | same handling; no show frame follows the first dark frame; the FFT thread keeps running (the wrapper returns) |
| Exception in MIDI mode | same abort | all-notes-off, plus SPACE (106) on the first stop since MIDI was enabled; app keeps running (Q6) |
| The same error on every frame | n/a | stop every time; traceback once, then one line at the 2nd, 4th, 8th… time (Q7) |
| Ctrl+C | `KeyboardInterrupt` in a slot → abort, no blackout | stop, then the window closes through `closeEvent` and the app quits (Q8) |
| MIDI port not open, or a MIDI send raises | n/a | nothing sent / logged per message; never raises; DMX already handled first |
| `closeEvent` blocks in PortAudio close or `fft_thread.wait()` | no blackout | blackout already sent; `wait(2000)` logs and continues |
| One blackout datagram lost | last look held | two more follow |
| Stop callable raises inside `trigger()` | n/a | logged; other stops still run; `triggered` stays True |
| `sync()` fails (disk full, locked file) | exception in a slot → abort | logged once, value stays in memory, retried on next flush |
| App killed (-9, power loss) | last look held | unchanged: only the node's own DMX-loss setting helps (hardware check) |
| `panic()` while DMX is off | n/a | sends nothing, logs at DEBUG (only dark frames until a `start()` after its queued `stop()`) |
| `panic()` at exit, window already deleted | n/a | dark frames still sent (Python state only); the guarded `emit` fails quietly |
| GUI thread descheduled mid-send when `panic()` runs elsewhere | n/a | after 5 ms the blackout goes out without the send lock; the frame in flight follows it, then a second blackout once that send is done (≤ 0.1 s), else the queued `stop()`'s |
| `start()` at the same moment as a `panic()` on another thread | n/a | the panic stays in force: its frames are blocked and its queued `stop()` stops the new run |
| Ctrl+C while the hook is already running | n/a | swallowed (every layer catches `BaseException`); inside `panic()` it cuts the blackout short and skips queueing `stop()`, but no show frame goes out (the panic stays in force). The app doesn't quit; Ctrl+C again does. Accepted. |

## Migration (each step leaves the app working)
1. `main_window.py:371-378`: `dmx_out.stop()` first, `dmx_out.close()` last; `engine.py:92` gets `wait(2000)`.
2. `dmx_output.py:156-163, 133-134`: `BLACKOUT_REPEATS`; update the packet counts in `tests/test_dmx_output.py` and
   `tests/test_main_window_dmx.py`.
3. `core/safety.py` + `DMXOutput.panic` (flag + send lock in `_send()`) + `_stop_requested` signal +
   `MIDIOutput.panic` + `BLACKOUT_NOTE`. `__main__.py:1-14`: console logging first, then the hook and
   `atexit.register(stop.trigger, 'exit')`, all before `QApplication`. `MainWindow.__init__` registers `'dmx'` and
   `'midi'`; switching Control Mode to MIDI, or opening a MIDI port, re-arms SPACE; `closeEvent` unregisters both
   last. Plan:
   `docs/plans/task-3-emergency-stop.md`.
4. `settings_store.py:83-87`: deferred sync + `flush()`; `main_window.py` flushes in `closeEvent` before step 1's
   `dmx_out.close()`; rewrite `tests/test_settings_store.py:77-81`.
5. `engine.py:154-188`: reorder emits; add the ordering test; golden unchanged.

## Tests
- CI: everything above (fake sockets, fake audio, offscreen Qt). The abort case is testable because the hook replaces
  `qFatal`: raise inside a slot connected to a test signal, assert the process is still here and `fake_udp.sent` ends
  with three dark frames. The FFT-thread case runs with the DMX timer going and the FFT thread's sends slowed down,
  and asserts no non-dark frame follows the first dark one (and that a tick actually ran during the panic). The send
  lock, the second blackout after a stuck send and the SPACE arm's lock each have a deterministic test that pauses
  one thread mid-step (a patched `build_artdmx`, or the arm's read) and fails without the lock or fix. `atexit` via a
  subprocess, also with the Qt object deleted.
- Hardware: close the app with the laser lit; `configure()` to another IP while lit; pull the node's cable, then
  plug it back; and the DMX-loss behaviour of the CR011R itself (hold vs. dark), written into the README.

## Dependencies
None. `app-object.md` later moves the registration into the app object; `frame-clock.md` adds "frame source raised"
as another trigger of the same stop.

## Open questions
- **Q1.** After an unhandled exception and the blackout: keep the window open with DMX output stopped (user re-enables
  by switching Control Mode), or show a message and quit? **Decided: keep running.** DMX output is stopped, the
  Control Mode dropdown is left as it was, and the user re-enables DMX by switching Control Mode (to MIDI and back).
  No dialog, no quit: `on_handled` only logs that hint.
- **Q2.** In MIDI mode, should the emergency stop also send something (the SPACE note 106, or MIDI all-notes-off) so
  SoundSwitch goes to its blackout look? Today the stop only knows DMX. **Decided: yes, both.** A second stop
  callable, `'midi'`, registered after `'dmx'`, sends MIDI all-notes-off and the SPACE note (106) through
  `MIDIOutput.panic()`. It sends nothing outside MIDI mode or while no MIDI port is open, and never raises. Order:
  all-notes-off (controller 123 on channel 1) first, then SPACE Note ON and its Note OFF, back to back. SPACE is then
  the last thing SoundSwitch receives, and its Note OFF is the same release every key press already sends 50 ms after
  the ON, which today doesn't end a look. Sent after SPACE, all-notes-off would release SPACE too; probably harmless
  for the same reason, but how SoundSwitch treats controller 123 is unchecked, so it goes first. SPACE goes out at
  most once per MIDI enable (Q10). Details: `docs/plans/task-3-emergency-stop.md`.
- **Q3.** `FLUSH_MS = 400`: a killed app loses at most that much of settings changes. Acceptable, or lower (200)?
- **Q4.** Does the CR011R have a DMX-loss setting? Needs the manual or a test with the cable pulled.
- **Q5.** Three blackout frames back to back, or spread over three ticks (75 ms) when the timer is still alive?
  ASSUMPTION(Q5): back to back (`BLACKOUT_REPEATS` in `dmx_output.py`); spreading them is a change to `_blackout()` only.
- **Q6.** In MIDI mode, should anything stop cues after the emergency stop? **Decided: no.** Cues keep flowing; the
  next sound-mode or keyboard cue lights SoundSwitch again.
- **Q7.** How should an error that repeats (e.g. on every audio frame) be logged? **Decided:** the stop runs every
  time; the traceback is logged once, then one line at the 2nd, 4th, 8th… occurrence (same type, file and line).
- **Q8.** What should Ctrl+C (a `KeyboardInterrupt` reaching the hook) do? **Decided: stop, then quit normally.** The
  stop runs, one WARNING line is logged, and `on_interrupt` queues `QApplication.closeAllWindows`, so `closeEvent`
  runs as if the user closed the window and the app quits. The app doesn't keep running.
- **Q9.** All-notes-off on which channels? **Decided: channel 1 only**, the only channel PyLZR sends on.
- **Q10.** What if SPACE toggles rather than latches in SoundSwitch? **Decided: don't rely on it latching.** The SPACE
  note goes out only on the first emergency stop after MIDI output is (re)enabled; later stops send all-notes-off only.
  Switching Control Mode to MIDI re-arms it, and so does opening a MIDI port (Q12). Whether SPACE latches is still
  worth knowing (manual check), but nothing depends on it.
- **Q11.** Does a stop that couldn't deliver SPACE (no port open, Note ON failed) use up the arm?
  ASSUMPTION(Q11): no. The arm is used up by the first SPACE that reaches the port, so SoundSwitch still receives it
  at most once per enable. Making any stop use it up is one line in `MainWindow._midi_emergency_stop`.
- **Q12.** Should opening a different MIDI port re-arm SPACE? **Decided: yes.** SoundSwitch on the new port hasn't
  received SPACE through it. Every successful open re-arms (`MainWindow._open_midi_port`): the user choosing a port,
  Reset, the saved port at startup, and the default port reconnecting (e.g. loopMIDI started after PyLZR). A failed
  open leaves the arm as it was.
