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
    def trigger(self, reason: str) -> None     # runs every stop once, in registration order; a stop that raises
                                              # is logged and the rest still run; never raises; re-entrant safe
    @property
    def triggered(self) -> bool

def install_excepthook(stop: EmergencyStop, on_handled: Callable[[], None] | None = None) -> None
    # sets sys.excepthook and threading.excepthook; the handler logs the traceback (ERROR, logger 'pylzr.safety'),
    # calls stop.trigger('unhandled exception'), then on_handled() (what the app does next: see Q1)

# src/pylzr/dmx/dmx_output.py
BLACKOUT_REPEATS = 3
def stop(self) -> None          # as today, but sends BLACKOUT_REPEATS dark frames before setting status 'off'
def configure(...) -> bool      # the old node gets BLACKOUT_REPEATS dark frames while active
def panic(self) -> None         # from any thread: send BLACKOUT_REPEATS dark frames through the sender directly,
                                # swallow every error, then emit _stop_requested (queued) so the GUI thread runs stop()

# src/pylzr/gui/settings_store.py
FLUSH_MS = 400
def set(self, key, value) -> None   # stores the value, (re)starts the flush timer; syncs at once with no QCoreApplication
def flush(self) -> None             # sync now, stop the timer
def clear(self) -> None             # flushes

# src/pylzr/engine.py  (order only; no new names)
```
Ownership: `main()` creates the `EmergencyStop` and installs the hook before any Qt object exists; `MainWindow`
registers `dmx_out.panic` under the name `'dmx'` (later the app object does, see `app-object.md`). The store owns its
timer. `DMXOutput` owns the blackout policy.

## Threading / timing
- `sys.excepthook` runs on the thread that raised. PyQt5 wraps every slot call: with a custom hook installed it is
  called instead of `qFatal()`, on the GUI thread for GUI slots and on the FFT thread for `FFTWorker.process`.
  `threading.excepthook` covers plain threads (PortAudio's callback thread is not a Python thread; an exception there is
  swallowed by PyAudio and must not be relied on).
- `panic()` may run on any thread: it only touches the socket (`UdpSender.send`, thread-safe for one datagram at a
  time) and emits a queued signal. `QTimer.stop()` happens on the GUI thread via that signal. If the GUI thread is
  the one that raised, the queued stop runs on the next event-loop pass, after the handler returns.
- Deadline: dark frames leave within one tick (25 ms) of the trigger. The three sends are back to back (microseconds);
  spacing them over ticks would need the timer that may be the thing that failed.
- Settings: `set()` on the GUI thread; the flush timer fires on the GUI thread; one `sync()` costs 2–4 ms measured,
  so at most one such stall per `FLUSH_MS` of user input instead of one per slider step.
- Engine order: `_process_chunk` queues the FFT before drawing the waveform; `_on_spectrum` runs the analyzer, sound
  mode and cue before emitting `spectrum_ready` (plot redraw). Same thread, same values, less time before the cue.

## Failure modes
| Failure | Today | After this phase |
|---|---|---|
| Exception in a GUI slot | process aborts, node holds last look | traceback logged, 3 dark frames, DMX stopped, then Q1 |
| Exception in `FFTWorker.process` | same abort | same handling; the FFT thread keeps running (the wrapper returns) |
| `closeEvent` blocks in PortAudio close or `fft_thread.wait()` | no blackout | blackout already sent; `wait(2000)` logs and continues |
| One blackout datagram lost | last look held | two more follow |
| Stop callable raises inside `trigger()` | n/a | logged; other stops still run; `triggered` stays True |
| `sync()` fails (disk full, locked file) | exception in a slot → abort | logged once, value stays in memory, retried on next flush |
| App killed (-9, power loss) | last look held | unchanged: only the node's own DMX-loss setting helps (hardware check) |
| `panic()` while DMX is off | n/a | sends nothing, logs at DEBUG |

## Migration (each step leaves the app working)
1. `main_window.py:371-378`: `dmx_out.stop()` first, `dmx_out.close()` last; `engine.py:92` gets `wait(2000)`.
2. `dmx_output.py:156-163, 133-134`: `BLACKOUT_REPEATS`; update the packet counts in `tests/test_dmx_output.py` and
   `tests/test_main_window_dmx.py`.
3. `core/safety.py` + `DMXOutput.panic` + `_stop_requested` signal; `__main__.py:7-14` installs the hook before
   `QApplication`; `MainWindow.__init__` registers `'dmx'`; `atexit.register(stop.trigger, 'exit')`.
4. `settings_store.py:83-87`: deferred sync + `flush()`; `main_window.py` flushes in `closeEvent` before step 1's
   `dmx_out.close()`; rewrite `tests/test_settings_store.py:77-81`.
5. `engine.py:154-188`: reorder emits; add the ordering test; golden unchanged.

## Tests
- CI: everything above (fake sockets, fake audio, offscreen Qt). The abort case is testable because the hook replaces
  `qFatal`: raise inside a slot connected to a test signal, assert the process is still here and `fake_udp.sent` ends
  with three dark frames. `atexit` via a subprocess.
- Hardware: close the app with the laser lit; `configure()` to another IP while lit; pull the node's cable, then
  plug it back; and the DMX-loss behaviour of the CR011R itself (hold vs. dark), written into the README.

## Dependencies
None. `app-object.md` later moves the registration into the app object; `frame-clock.md` adds "frame source raised"
as another trigger of the same stop.

## Open questions
- **Q1.** After an unhandled exception and the blackout: keep the window open with DMX output stopped (user re-enables
  by switching Control Mode), or show a message and quit? Default in `PLAN.md` is "keep running, stopped".
- **Q2.** In MIDI mode, should the emergency stop also send something (the SPACE note 106, or MIDI all-notes-off) so
  SoundSwitch goes to its blackout look? Today the stop only knows DMX.
- **Q3.** `FLUSH_MS = 400`: a killed app loses at most that much of settings changes. Acceptable, or lower (200)?
- **Q4.** Does the CR011R have a DMX-loss setting? Needs the manual or a test with the cable pulled.
- **Q5.** Three blackout frames back to back, or spread over three ticks (75 ms) when the timer is still alive?
