# Design: D2.5 fail-safe output

## Scope
Make every abnormal exit, and every ordinary one, leave the laser dark, keep the GUI thread's own work from
delaying DMX frames, and notice when audio stops or never starts. Covers audit P2 (shutdown order), P3 (repeated
blackout), P1 (exception hook + emergency stop), P5 (debounced settings writes), P7 (cue logic before redraws), P4
(audio-stall detection, Task 6) and P6 (starting without an input device, Task 7). Out of scope: bounding the chunk
queue (P8, folded into D4 next to the analysis worker, `d4-dynamic-sound-mode.md`), moving analysis off the GUI thread
(D4), and anything the node does on its own when DMX stops (a hardware setting, checked by hand).

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
                                                   # True if the note's ON was sent. Task 6: `note` is skipped when it
                                                   # is already last_note (Q21)
# Task 6 (Q21), all under the send lock:
@property
def last_note(self) -> int | None                  # the last Note ON sent on this port (press_note or panic);
                                                   # None after open(), close() or forget_last_note()
def forget_last_note(self) -> None                 # MIDI (re)enabled: a fresh start, like the SPACE arm (Q10)
def press_note(self, note: int, *, skip_if_last: bool = False) -> None   # skip_if_last: send nothing if `note` is
                                                   # already last_note (check and send are one step under the lock)

# src/pylzr/core/protocols.py, core/output_switch.py, dmx/dmx_output.py  (Task 6)
def press_note(self, note: int, *, skip_if_last: bool = False) -> None   # NoteOutput; the switch forwards it, DMX
                                                                         # ignores it (no SPACE look to toggle)
# src/pylzr/midi/key_map.py
BLACKOUT_NOTE = 106             # SPACE; SoundSwitch's blackout look

# src/pylzr/gui/settings_store.py
FLUSH_MS = 400
def set(self, key, value) -> None   # stores the value, (re)starts the flush timer; syncs at once with no QCoreApplication
def flush(self) -> None             # sync now, stop the timer
def clear(self) -> None             # stops the timer, clears, syncs now
@property
def pending(self) -> bool           # a change is waiting for the flush timer
class _DeferredSettings(QSettings)  # private: ignores Qt's UpdateRequest, so only sync() (or the destructor) writes (Q14)

# src/pylzr/engine.py  (P7: order only; no new names)

# src/pylzr/audio/stall.py  (P4, Task 6; pure Python, no Qt)
StallEvent = Literal['stalled', 'resumed']
class StallWatch:
    def __init__(self, timeout_s: float, clock: Callable[[], float] = time.monotonic)
    def chunk(self) -> None             # any thread (PortAudio's callback): a chunk arrived now; one store, never raises
    def restart(self) -> bool           # capture (re)started: the wait starts afresh; True if that cleared a stall
    def check(self) -> StallEvent | None   # owner's thread: 'stalled' once when no chunk for timeout_s,
                                           # 'resumed' once when a chunk arrives after that; else None
    @property
    def stalled(self) -> bool

# src/pylzr/engine.py  (P4, Task 6)
STALL_TIMEOUT_S = 2.0           # no chunk for this long while capturing = stalled (Q16)
STALL_CHECK_MS  = 250           # how often the GUI thread looks
audio_status_changed = pyqtSignal(bool, str)   # ok, detail: (False, 'No audio') on a stall, (True, device) on recovery
@property
def audio_stalled(self) -> bool

# src/pylzr/analysis/sound_mode.py  (P4, Task 6)
def go_quiet(self) -> bool      # LOW 0 / HIGH 0 (the SPACE cue, as for silence) if not already there; True if issued
def update_mode(self)           # Task 6: the SPACE cue goes out with skip_if_last=True, every other cue as today (Q21)

# src/pylzr/analysis/analyzer.py  (P4, Task 6)
def reset(self) -> None         # today's private _reset(), made public: drop the partly filled window

# src/pylzr/audio/audio_input.py  (P6, Task 7)
def __init__(...)               # no longer raises when no input can be opened: logs it, _stream None, device_name None
device_name: str | None         # None: no input open
error: str | None               # why the last open failed (shown in Settings), None once one succeeds
def start(self) / stop(self)    # also record whether capture is wanted, so a stream opened later starts capturing
def switch_device / refresh_devices   # work from the no-input state; a new stream starts if capture is wanted
```
Ownership: `main()` sets up console logging, creates the `EmergencyStop`, installs the hook and registers
`atexit.register(stop.trigger, 'exit')`, all before any Qt object exists, then passes it to `MainWindow(safety=…)`.
`MainWindow` registers `dmx_out.panic` under the name `'dmx'`, then `'midi'` (in MIDI mode: all-notes-off, plus SPACE
once per MIDI enable or MIDI port opened, Q10, Q12), and owns the SPACE arm. Later the app object does this, see `app-object.md`. The store
owns its timer. `DMXOutput` owns the blackout policy. `AudioEngine` owns the `StallWatch`, its check timer and the
stall response (P4); `AudioInput` owns the no-input state (P6); the window only shows `audio_status_changed`.
`MIDIOutput` owns `last_note`, the one record of what SoundSwitch received last, which both automatic SPACE senders
(sound mode's quiet cue, the emergency stop) check under its send lock (Q21).

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
- SPACE from two automatic senders (Task 6, Q21): sound mode's quiet cue (on the GUI thread: a quiet window, a stall,
  sound mode turned on) and the emergency stop (any thread). Both check `MIDIOutput.last_note` and send under the
  MIDI send lock, so whichever comes second sees the first one's SPACE and skips it, whatever the threads. Switching
  Control Mode to MIDI forgets `last_note` together with re-arming SPACE (before the switch), and opening a port
  starts it at None, so the scope is the same as the arm's (Q10, Q12). The keyboard's SPACE key never skips.
- `KeyboardInterrupt` is raised on the main thread only; `on_interrupt` queues the close there (`QTimer.singleShot`),
  so `closeEvent` never runs inside the hook.
- Deadline: dark frames leave within one tick (25 ms) of the trigger. The stop runs before any logging. The three sends
  are back to back (microseconds); spacing them over ticks would need the timer that may be the thing that failed.
- Settings: `set()` on the GUI thread; the flush timer fires on the GUI thread; one `sync()` costs 2–4 ms measured,
  so one such stall per pause of `FLUSH_MS` in changes (a continuous drag writes once, after it ends), plus one on
  close, instead of one per slider step. Plain `QSettings` would also write on the next event-loop pass after any
  change (it posts itself an `UpdateRequest`); the store's subclass ignores that event (Q14).
- Engine order: `_process_chunk` queues the FFT before drawing the waveform; `_on_spectrum` runs the analyzer, sound
  mode and cue before emitting `spectrum_ready` (plot redraw). Same thread, same values, less time before the cue.
- Audio stall (P4): PortAudio's callback thread stamps `StallWatch.chunk()` (one float store and one counter
  increment, single writer) before it queues the chunk. The GUI thread checks every `STALL_CHECK_MS` (250 ms) while
  the engine is started. A stall is declared 2.0–2.25 s after the last chunk. The stamp comes from the callback
  thread, not from `_process_chunk`, so a busy GUI thread never looks like a stall: the check can't run while the
  GUI thread is blocked, and when it does run the stamp is fresh. A check that itself comes over `STALL_TIMEOUT_S`
  late (the computer slept, or the GUI thread was blocked) restarts the wait instead of declaring a stall. The quiet
  cue goes out on the GUI thread, the thread `_on_spectrum` already sends cues from, so `SoundMode` is never touched
  from two threads. Not the emergency stop (Q15).
- No input device (P6): all on the GUI thread, as today. `AudioInput` records whether capture is wanted, so a stream
  opened later (rescan, device switch) starts capturing. While no stream is open the engine skips the stall check
  (the state is known and already shown); opening one restarts the watch.

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
| `sync()` fails (disk full, locked file, folder not creatable) | silent: `QSettings.sync()` doesn't raise, `status()` reports it and nobody reads it | logged once per store (WARNING, names the file); the value stays in memory (`get()` returns it) and the next successful sync writes it (next change, or close). Recovery isn't logged: `status()` keeps its first error. |
| Settings changed, then the app is killed | nothing lost (every change written at once) | changes since input last paused for `FLUSH_MS` are lost (Q3); a normal close and Ctrl+C write them (`closeEvent` flushes) |
| App killed (-9, power loss) | last look held | unchanged: only the node's own DMX-loss setting helps (hardware check) |
| `panic()` while DMX is off | n/a | sends nothing, logs at DEBUG (only dark frames until a `start()` after its queued `stop()`) |
| `panic()` at exit, window already deleted | n/a | dark frames still sent (Python state only); the guarded `emit` fails quietly |
| GUI thread descheduled mid-send when `panic()` runs elsewhere | n/a | after 5 ms the blackout goes out without the send lock; the frame in flight follows it, then a second blackout once that send is done (≤ 0.1 s), else the queued `stop()`'s |
| `start()` at the same moment as a `panic()` on another thread | n/a | the panic stays in force: its frames are blocked and its queued `stop()` stops the new run |
| Ctrl+C while the hook is already running | n/a | swallowed (every layer catches `BaseException`); inside `panic()` it cuts the blackout short and skips queueing `stop()`, but no show frame goes out (the panic stays in force). The app doesn't quit; Ctrl+C again does. Accepted. |
| Audio callbacks stop (device unplugged, exclusive-mode grab, driver hang) | nothing notices; sound mode holds its last cue; fps 0 shown only while Settings is open | after 2 s: one WARNING in the in-app console (and the terminal) saying what happened and what to do, audio dot red ("No audio"), and with sound mode on the quiet cue (LOW 0 / HIGH 0, SPACE) if the mode isn't already quiet. DMX output and the tester are untouched (Q15) |
| A stall and an emergency stop, either order, or two stalls, in MIDI mode | n/a | SPACE reaches SoundSwitch once: the second sender finds SPACE is already the last note on the port and skips it (all-notes-off still goes out from the stop; the arm stays set, Q11). Two stalls with a lit cue between send SPACE once after each lit cue, the same pattern as any two quiet passages (Q21) |
| PortAudio stops the stream on its own (`is_active` turns False) | same | same as above: the watch tracks "capture wanted" (engine started), not `is_active` |
| Audio comes back | n/a | one INFO line in the console, dot green with the device name; the next full window sends its cue as usual |
| Console set to "Quiet" in Settings | n/a | neither line shows (the user hid everything); the dot still shows the stall |
| Computer sleeps and wakes | n/a | the late check restarts the wait; if the stream died, the stall is declared 2 s after wake. No automatic reopen: the warning says to press ↻ (Q17) |
| Very quiet input (chunks of near-zero samples) | quiet cue through the normal path | unchanged: it is sound, not a stall. All-zero input from a driver that keeps calling back after unplug looks the same (Q18) |
| No usable input device at startup (none, all busy, PortAudio fails to start) | `AudioInput.__init__` raises, the window never opens, traceback | the app opens; WARNING with the reason; audio dot red ("No input device"); keyboard cues, MIDI, DMX and the tester work; ↻ opens a device plugged in later and starts capturing (Q20) |

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
4. `settings_store.py`: deferred sync (`_DeferredSettings`, flush timer) + `flush()`; `main_window.py` flushes in
   `closeEvent` right after `dmx_out.stop()` and `_close_dmx_tester()`, before `engine.shutdown()`; replace
   `tests/test_settings_store.py:77-81`. Plan: `docs/plans/task-4-debounced-settings.md`.
5. `engine.py:154-188`: reorder emits; add the ordering test; golden unchanged.
6. New `audio/stall.py` (`StallWatch`); `engine.py`: stamp chunks on the callback thread, check timer, stall and
   recovery handling, `audio_status_changed`; `SoundMode.go_quiet()`; `AudioAnalyzer.reset()` public;
   `main_window.py` shows `audio_status_changed`; `tests/conftest.py` turns stalls off for every test that doesn't
   ask for them. SPACE (Q21): `MIDIOutput.last_note`, `forget_last_note()`, `press_note(…, skip_if_last=)` through
   `NoteOutput`, `OutputSwitch` and `DMXOutput`; `panic()` skips a repeat; sound mode's SPACE cue asks to skip;
   switching Control Mode to MIDI forgets. Golden unchanged. Plan: `docs/plans/task-6-audio-stall.md`.
7. `audio_input.py`: a failed open at construction leaves no stream instead of raising; capture-wanted state;
   `switch_device`/`refresh_devices` from no stream; `main_window.py` shows "No input device"; the fake PyAudio can
   have no input devices. Plan: written when Task 6 is done.

## Tests
- CI: everything above (fake sockets, fake audio, offscreen Qt). The abort case is testable because the hook replaces
  `qFatal`: raise inside a slot connected to a test signal, assert the process is still here and `fake_udp.sent` ends
  with three dark frames. The FFT-thread case runs with the DMX timer going and the FFT thread's sends slowed down,
  and asserts no non-dark frame follows the first dark one (and that a tick actually ran during the panic). The send
  lock, the second blackout after a stuck send and the SPACE arm's lock each have a deterministic test that pauses
  one thread mid-step (a patched `build_artdmx`, or the arm's read) and fails without the lock or fix. `atexit` via a
  subprocess, also with the Qt object deleted.
- Audio stall: `StallWatch` with a fake clock (stall, resume, late check, restart); the engine with a fake-clock watch
  and its check called directly (quiet cue once, recovery, sound mode on during a stall); one window test end to end
  with a short real timeout. Every other test runs with stalls turned off (`STALL_TIMEOUT_S = inf`, autouse fixture),
  since most windows live for a while without audio. The warning and the recovery line appear in the in-app console
  at its default level, with the warning icon. SPACE (Q21): a stall then an emergency stop, an emergency stop then a
  stall, two stalls (quiet between: one SPACE; a lit cue between: one after each), sound mode toggled during a stall;
  and a deterministic two-thread test that `panic()` and a skipping `press_note` send SPACE once.
- No input device: the fake PyAudio with no input devices, or `fail_open = {0}`: the window opens, shows "No input
  device", sends keyboard cues; a device added and ↻ starts capture.
- Hardware: close the app with the laser lit; `configure()` to another IP while lit; pull the node's cable, then
  plug it back; and the DMX-loss behaviour of the CR011R itself (hold vs. dark), written into the README.

## Dependencies
None. `app-object.md` later moves the registration into the app object and forwards `audio_status_changed`;
`frame-clock.md` adds "frame source raised" as another trigger of the same stop. D4's analysis worker
(`d4-dynamic-sound-mode.md`) moves the stall check and the quiet cue onto the worker's thread with `SoundMode`.

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
- **Q3.** `FLUSH_MS = 400`: acceptable, or lower (200)? **Decided: keep 400.** The wait restarts on every change, so
  a killed app loses the changes made since input last paused for 400 ms (during a continuous slider drag, the drag
  so far). A normal close and Ctrl+C write everything (`closeEvent` flushes). Plan:
  `docs/plans/task-4-debounced-settings.md`.
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
  worth knowing (manual check), but nothing depends on it. Task 6 extends this to sound mode's own SPACE cue, so a
  stall and an emergency stop together send SPACE once (Q21).
- **Q11.** Does a stop that couldn't deliver SPACE (no port open, Note ON failed) use up the arm?
  ASSUMPTION(Q11): no. The arm is used up by the first SPACE that reaches the port, so SoundSwitch still receives it
  at most once per enable. Making any stop use it up is one line in `MainWindow._midi_emergency_stop`.
- **Q12.** Should opening a different MIDI port re-arm SPACE? **Decided: yes, on every successful open, reconnects
  included** (confirmed after Task 3). SoundSwitch on the port hasn't received SPACE through that connection. Every
  successful open re-arms (`MainWindow._open_midi_port`): the user choosing a port, Reset, the saved port at startup,
  and the default port reconnecting (e.g. loopMIDI started after PyLZR). A failed open leaves the arm as it was.
- **Q13.** Should settings get an extra flush on exit paths that skip `closeEvent` (`atexit`, `aboutToQuit`)?
  **Decided: no.** No such path exists today (nothing calls `QApplication.quit()`; Ctrl+C closes the windows). If one
  appears, Qt's `QSettings` destructor writes pending changes when the window and its store are freed. An `atexit`
  flush registered in `main()` would run before the emergency stop's `atexit` blackout (last in, first out), and
  `aboutToQuit` fires before `exec_()` returns, so either would put file I/O ahead of the blackout. Reversible: one
  line in `main()`.
- **Q14.** How is Qt's own automatic write held back? **Decided: a `QSettings` subclass whose `event()` ignores
  `QEvent.UpdateRequest`**, not pending values kept in a Python dict. It keeps `get()`, cache sharing between stores
  in one process, the destructor write and `clear()` as they are. It relies on how Qt 5.15 implements the automatic
  sync; two tests in `tests/test_settings_store.py` pin it, and the PyQt6 spike re-checks it (`ROADMAP.md`).
- **Q15.** What should a stall do to the output: the quiet cue, or the Task 3 emergency stop? **Decided: the quiet
  cue** through sound mode (LOW 0 / HIGH 0, which is SPACE, SoundSwitch's blackout look), only while sound mode is
  on, and only if the mode isn't already quiet; no emergency stop, no DMX change. Reasons: the emergency stop is for
  "the program is in an unknown state" and needs the user to switch Control Mode before DMX sends again, while a
  stall is a known outside condition that should end by itself when audio returns; the quiet cue is exactly what real
  silence would send, so the operator's quiet look applies; and DMX content isn't cue-driven yet (the tester's
  override layer is the only DMX content, and someone testing the laser with no microphone mustn't be blacked out).
  After D3 the quiet cue reaches DMX through the cue→scene map; what a stall should do then is `d3-scenes.md` Q6.
- **Q16.** How long is a stall? **Decided: `STALL_TIMEOUT_S = 2.0`** (43 missing chunks, two averaging windows at
  the default rate), **checked every `STALL_CHECK_MS = 250`**. Long enough that no driver hiccup trips it; short
  enough that the stage goes quiet within about two cue periods. Both are constants in `engine.py`.
- **Q17.** Should PyLZR reopen the device by itself after a stall? **Decided for now: no.** Restarting PortAudio
  (`refresh_devices`) blocks the GUI thread and pauses every input; the warning tells the user to press ↻ in
  Settings. Recovery without a rescan (the driver resumes callbacks) is detected and logged. A possible later
  improvement: see "Later improvements".
- **Q18.** Is digital silence (every sample 0 for many seconds) a stall? **Decided: no.** It's sound, and sound mode
  already sends the quiet cue for it through the normal path; only missing callbacks count. A driver that keeps
  calling back with zeros after an unplug therefore gets the quiet cue but no warning.
- **Q19.** How is a device that keeps dropping out logged? **Decided: one WARNING per stall and one INFO per
  recovery, no rate limit.** Each stall lasts at least 2 s, so that's at most one pair every ~2 s, and each line is
  useful when diagnosing a bad cable.
- **Q20.** With no input device at startup, should PyLZR retry on a timer? **Decided: no, ↻ only** (as the audit
  says), for the same reason as Q17.
- **Q21.** How does the stall's quiet cue (SPACE in MIDI mode) stay consistent with Q10–Q12, which don't rely on
  SPACE latching? Sound mode already sends SPACE as its normal quiet cue (`MODE_MAP[0][0]` is note 106, sent with no
  dual-mode offset) whenever the mode changes to LOW 0 / HIGH 0, and the stall uses that same path (`go_quiet` →
  `update_mode`). Sound mode alone never sends SPACE twice in a row: its mode guard needs a different cue in
  between. But a stall's SPACE followed by an emergency stop (whose arm knows nothing of sound mode), or an
  emergency stop's SPACE followed by a stall or a quiet window, would send SPACE twice in a row.
  ASSUMPTION(Q21): **no automatic SPACE goes out when SPACE is already the last note sent on the port.**
  `MIDIOutput` records the last Note ON (`last_note`); sound mode sends its SPACE cue with `skip_if_last=True`, and
  `panic()` skips its note the same way, both checked and sent under the MIDI send lock. The arm (Q10) still limits
  the emergency stop to once per enable; a skipped SPACE doesn't use it up (Q11). Switching Control Mode to MIDI
  forgets `last_note` as it re-arms, and a newly opened port starts with none, so the boundaries are Q10's and
  Q12's. The SPACE key on the keyboard is never skipped (a person pressing it twice means it). Sharing the arm
  instead was rejected: it is once per MIDI enable, so a second stall hours later would send no quiet cue at all,
  and the arm lives in the window while the cue comes from the engine. Side effect: sound mode turned off and on in
  quiet music no longer resends SPACE when SPACE was the last note sent.

## Later improvements
- **Reopen the input automatically after a stall** (Q17). After a stall, try `refresh_devices()` on a back-off timer
  (5 s, 10 s, 20 s …) until audio returns or the user picks a device. Needs: a measure of how long a PortAudio restart
  blocks the GUI thread on Windows (WASAPI, MME) and macOS, since it pauses every input, ideally with the restart
  moved off the GUI thread first (D4's analysis worker); and a check that reopening by name can't pick a different
  device with the same name. Task 7's "no input device at startup" (Q20) would share the timer.
