# Task 3: exception hook and emergency stop (P1): implementation plan

Branch `hayden/components-pt3`, after `25e92de Send the blackout three times (P3)`. Task text: `PLAN.md`, Task 3.
Design: `docs/design/safety-phase.md` (Interfaces, Threading, Failure modes, Open questions).
Baseline: `pytest -q` gives **1318 passed**.

Decisions in force (all recorded in the design's Open questions):
- **Q1.** After an unhandled exception and the blackout, the app keeps running with DMX output stopped. The Control
  Mode dropdown stays as it was; the user re-enables DMX by switching Control Mode (to MIDI and back to DMX).
- **Q2.** In MIDI mode the emergency stop also sends MIDI all-notes-off and the SPACE note (106), so SoundSwitch goes
  to its blackout look. It's a second stop callable, `'midi'`. All-notes-off goes first (§3.4).
- **Q6.** MIDI cues keep flowing after the stop: the next cue lights SoundSwitch again.
- **Q7.** A repeating error runs the stop every time, but logs its traceback once, then one line at the 2nd, 4th,
  8th… time.
- **Q8.** `KeyboardInterrupt` (Ctrl+C) triggers the stop, then quits through the normal close path (`closeEvent`, as
  if the user closed the window). It doesn't keep running.
- **Q9.** All-notes-off goes on channel 1 only.
- **Q10.** The stop doesn't rely on SPACE latching in SoundSwitch. SPACE is sent only by the first stop after MIDI
  output is (re)enabled; later stops send all-notes-off only. Switching Control Mode to MIDI re-arms it.
- **M2.** No show frame may go out after `panic()` starts. A flag that `_send()` checks under a short lock closes the
  gap (§3.3, §5).

One assumption left: **ASSUMPTION(Q11)**. The SPACE arm is used up by the first SPACE that actually reaches the MIDI
port. A stop that couldn't send it (no port open, or the Note ON send failed) leaves it armed. Either reading keeps
the safety property (SoundSwitch never receives SPACE twice per enable); changing it is one line (§3.6).

---

## 1. What the user sees afterwards

| Situation | Today | After Task 3 |
|---|---|---|
| A slot raises on the GUI thread, DMX mode | `qFatal` → process aborts, laser holds its look | 3 dark frames at once; from then on only dark frames; on the next event-loop pass `stop()` (3 more dark frames, status Off, timer stopped); one traceback in the log; one hint line; the window stays open with Control Mode still on DMX |
| `FFTWorker.process` raises (FFT thread), DMX mode | same abort | same as above; the hook runs on the FFT thread; no show frame follows the first dark frame; the FFT thread keeps processing later chunks |
| A slot raises, MIDI mode | abort | no DMX; MIDI CC 123 (all notes off), Note ON 106, Note OFF 106; the app keeps running; the next cue lights the show again (Q6) |
| A second (or later) stop in MIDI mode | n/a | all-notes-off only, until Control Mode is switched to MIDI again (Q10) |
| Ctrl+C in the terminal | `KeyboardInterrupt` in the next slot → abort, no blackout | stop, one WARNING line, then every window closes on the next event-loop pass. `closeEvent` runs (P2 order) and the app quits (Q8). |
| Exception in a plain `threading.Thread` | traceback printed, thread dies, app runs on | same stop and logging as a slot exception |
| Exception escapes `MainWindow()` during startup (DMX restored from settings) | traceback, exit, laser holds the look | stop runs from the top-level hook, then again from `atexit`; process exits |
| Normal close | P2/P3 blackout in `closeEvent` | unchanged; `closeEvent` unregisters the stops last, so the `atexit` trigger finds nothing to do |

---

## 2. Doc fixes (accepted and applied)

Applied to `PLAN.md` and `docs/design/safety-phase.md` along with this revision:
- **M1.** Two blackouts: `panic()`'s 3 dark frames, then the queued `stop()`'s 3. Acceptance: "3 dark frames are sent
  before the hook returns; after the next event-loop pass `dmx_out.active` is False and the last 3 frames are dark".
- **M2 (changed).** The lit frame that could slip out in the FFT-thread case is not accepted. Closed by `_panicked` +
  `_send_lock` (§3.3); the explanation is in §5. Acceptance: "no non-dark frame follows the first dark frame".
- **M3.** Inside the hook: trigger first, then log the traceback, then `on_handled()` (first error only).
  `EmergencyStop.trigger` also runs the stops before logging its summary line.
- **M4.** `configure_console_logging()` goes first in `main()`, before `QApplication`.
- **M5.** `panic()` decides from Python state (`_closed`, `state`) and touches no Qt object until a guarded `emit`, so
  it works at exit after the window is gone.
- **M6.** No longer a race: `panic()` and `_send()` both send under `_send_lock`, so sequence numbers never repeat and
  `last_error`/`dropped` are written by one sender at a time. The design now says so.
- **M7.** PLAN.md line references (registration after `main_window.py:65`; `:12`, `:44`, `:261-272`, `:352`,
  `:371-382`) and the full file list.
- **M8.** PLAN.md header: 1318 tests before Task 3.
- **M9.** Design Interfaces / Ownership: `MIDIOutput.panic`, `BLACKOUT_NOTE`, the `'midi'` stop, `safety` parameter,
  `on_interrupt`.
- **M10.** Q6–Q11 recorded in the design's Open questions.

---

## 3. Changes by file

### 3.1 `src/pylzr/core/safety.py` (new, pure Python: no Qt import)

```python
"""Emergency stop: what runs when something goes wrong.

EmergencyStop holds named stop callables (black out the DMX output, send
SoundSwitch its blackout note, ...) and runs them all on trigger().
install_excepthook() makes every unhandled exception trigger it: in a Qt
slot on any thread (once sys.excepthook is replaced, PyQt calls it instead
of aborting), or in a plain Python thread. main() also triggers it at exit.

No Qt, so it can be installed before any Qt object exists.
See docs/design/safety-phase.md.
"""

import sys
import threading
import traceback
from collections.abc import Callable

from .app_logger import get_logger

log = get_logger('safety')        # 'pylzr.safety'


class EmergencyStop:
    """Named stop callables, run in registration order by trigger().

    trigger() may be called from any thread and never raises: a stop that
    raises is logged and the rest still run. A trigger() from inside a stop
    (same thread) returns at once. Triggers on different threads don't wait
    for each other, so a stop stuck on one thread can't hold up another.
    """

    def __init__(self):
        self._stops: dict[str, Callable[[], None]] = {}   # insertion order = run order
        self._lock = threading.Lock()                     # guards _stops only
        self._running = threading.local()                 # .active: this thread is inside trigger()
        self._triggered = False

    @property
    def triggered(self) -> bool:
        """True once trigger() has been called (never reset)."""
        return self._triggered

    def register(self, name: str, stop: Callable[[], None]) -> None:
        """Run `stop` on trigger(). Registering a name again replaces its
        callable and keeps its place in the order."""
        with self._lock:
            self._stops[name] = stop

    def unregister(self, name: str) -> None:
        """Forget `name`'s stop; an unknown name is ignored."""
        with self._lock:
            self._stops.pop(name, None)

    def trigger(self, reason: str) -> None:
        if getattr(self._running, 'active', False):
            return                                        # a stop triggered again: already running
        self._running.active = True
        try:
            self._triggered = True
            with self._lock:
                stops = list(self._stops.items())
            for name, stop in stops:                      # stops first: logging can be slow (M3)
                try:
                    stop()
                except BaseException:
                    log.exception(f'Emergency stop: "{name}" failed')
            if stops:
                log.warning(f'Emergency stop ({reason}): {", ".join(name for name, _ in stops)}')
            else:
                log.debug(f'Emergency stop ({reason}): nothing registered')
        finally:
            self._running.active = False


def install_excepthook(stop: EmergencyStop, on_handled: Callable[[], None] | None = None,
                       on_interrupt: Callable[[], None] | None = None) -> None:
    """Make every unhandled exception call stop.trigger(...) first, then log
    it (ERROR, with traceback; a repeating error once, then one line at the
    2nd, 4th, 8th… time), then, after the first one only, call on_handled()
    (what the app does next: design Q1). A KeyboardInterrupt (Ctrl+C) instead
    logs one WARNING line and calls on_interrupt() (design Q8: quit).
    Replaces sys.excepthook (main thread, and Qt slots on every thread) and
    threading.excepthook (Python threads). Doesn't chain to the previous hooks:
    they would print the traceback a second time. The hooks never raise."""
    handler = _ExceptionHandler(stop, on_handled, on_interrupt)
    sys.excepthook = handler.handle
    threading.excepthook = handler.handle_thread
```

`_ExceptionHandler` (module-private, same file):

| Member | Behaviour |
|---|---|
| `__init__(stop, on_handled, on_interrupt)` | stores all three; `self._seen: dict[tuple, int] = {}` keyed by `(exc_type, filename, lineno)` of the innermost traceback frame (holds no frames); `self._handled_once = False`; `self._lock = threading.Lock()` |
| `handle(exc_type, exc_value, exc_tb, thread_name=None)` | everything inside `try`. **Ctrl+C** (`issubclass(exc_type, KeyboardInterrupt)`): `self._stop.trigger('interrupted')`; `log.warning('Interrupted (Ctrl+C): outputs blacked out; quitting')`; `on_interrupt()` if given; return. Doesn't count as a handled error: no traceback, no `on_handled`. **Otherwise:** **1.** `self._stop.trigger('unhandled exception')`; **2.** `self._log(...)` with `thread_name or threading.current_thread().name`; **3.** under the lock, flip `_handled_once`; if it was False and `on_handled` isn't None, call `on_handled()` after releasing the lock. `except BaseException: _last_resort(exc_type, exc_value, exc_tb)` |
| `handle_thread(args)` | `if args.exc_type is SystemExit: return` (as `threading`'s own hook does); else `self.handle(args.exc_type, args.exc_value, args.exc_traceback, args.thread.name if args.thread is not None else None)` |
| `_log(exc_type, exc_value, exc_tb, thread_name)` | under the lock: `count = self._seen[key] = self._seen.get(key, 0) + 1` with `key = _innermost(exc_type, exc_tb)`. `count == 1` → `log.error(f'Unhandled exception (thread {thread_name})', exc_info=(exc_type, exc_value, exc_tb))`. Q7: `count & (count - 1) == 0` (2, 4, 8, …) → `log.error(f'The same error again ({count} times so far): {exc_type.__name__}: {exc_value}')`. Any other count logs nothing. |
| `_innermost(exc_type, tb)` (module function) | walks `tb.tb_next` to the last frame; returns `(exc_type, tb.tb_frame.f_code.co_filename, tb.tb_lineno)`, or `(exc_type, None, None)` when `tb` is None |
| `_last_resort(*exc_info)` (module function) | `try: if sys.stderr is not None: traceback.print_exception(*exc_info, file=sys.stderr); traceback.print_exc(file=sys.stderr)` `except BaseException: pass` (pythonw has no stderr) |

Ruff 0.17.3 with `select = ["B", …]` accepts a bare `except BaseException:` (checked), so no `noqa` is needed.

### 3.2 `src/pylzr/__main__.py` (whole file, lines 1-18)

```python
import atexit
import sys

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from .core.app_logger import configure_console_logging, get_logger
from .core.safety import EmergencyStop, install_excepthook

log = get_logger('app')

# Design Q1: after an unhandled exception the outputs are blacked out and the app keeps running
KEEP_RUNNING_HINT = ('PyLZR keeps running with DMX output stopped: switch Control Mode to MIDI and back to DMX to '
                     'send again. In MIDI mode the next cue lights the show again.')


def _quit_as_if_closed():
    """Ctrl+C (design Q8): close every window on the next event-loop pass, the
    same path as the user closing them (closeEvent, then the app quits)."""
    if QApplication.instance() is not None:
        QTimer.singleShot(0, QApplication.closeAllWindows)


def main():
    configure_console_logging()          # first, so anything that fails from here on is logged (M4)
    safety = EmergencyStop()
    install_excepthook(safety, on_handled=lambda: log.warning(KEEP_RUNNING_HINT),
                       on_interrupt=_quit_as_if_closed)
    atexit.register(safety.trigger, 'exit')   # registered after PyQt's import, so it runs before PyQt's own exit cleanup
    app = QApplication(sys.argv)
    from .gui import MainWindow, style  # imported here so QApplication exists before any widget module loads
    style.apply(app)                     # before any window: fonts, palette, stylesheet, plot colours
    window = MainWindow(safety=safety)
    window.show()
    sys.exit(app.exec_())
```

`closeAllWindows` closes every visible top-level window: the main window, whose `closeEvent` closes the tester, plus
the tester if it's open. With `quitOnLastWindowClosed` (Qt's default) `exec_()` then returns and `main()` exits as
after a normal close. The close is queued, not called from inside the hook, so `closeEvent` (which waits up to 2 s for
the FFT thread) never runs inside PyQt's error handling. If Ctrl+C arrives before `exec_()` (during startup), the
interrupt is raised in `main()` itself: the top-level hook stops and logs, the queued close never runs, and the
process exits anyway.

### 3.3 `src/pylzr/dmx/dmx_output.py`

| Lines | Change |
|---|---|
| `:1-3` | add `import threading` (stdlib block) |
| after `:22` (`BLACKOUT_REPEATS`) | `_PANIC_LOCK_TIMEOUT_S = 0.005   # panic() waits at most this long for a send in progress (one sendto: microseconds)` |
| `:58-89` class docstring | `:62-64` "Everything runs on the GUI thread; one send takes microseconds." → "Everything runs on the GUI thread except panic(), which any thread may call; one send takes microseconds." After `:68` add: "panic() is the emergency stop (docs/design/safety-phase.md): from the moment it starts only dark frames go out, until the next start(); it sends the blackout BLACKOUT_REPEATS times at once, from whatever thread calls it, then has this object's thread run stop()." |
| after `:91` | `_stop_requested = pyqtSignal()   # from panic(), any thread: stop() runs on this object's thread` |
| after `:107` (`self._closed = False`) | `self._send_lock = threading.Lock()   # one frame at a time: panic() (any thread) vs the GUI thread's sends` and `self._panicked  = False              # set first thing by panic(): only dark frames go out until start()` |
| after `:119` | `self._stop_requested.connect(self.stop, Qt.QueuedConnection)`. It must be queued explicitly: with AutoConnection, a GUI-thread `panic()` would run `stop()` inside the exception hook. |
| `start()` `:152-161`, after `if self.active: return` | `if self._panicked: self._panicked = False; log.info('DMX: sending again after the emergency stop', extra={'tone': Tone.ON})`. It comes after the `active` check: if the output is still active, a queued `stop()` is pending, and the flag must stay set until that stop has run. |
| `_send()` `:213-217` | replace (below) |
| new methods after `close()` (`:179`), in the Lifecycle section | `panic()` and `_send_blackout_now()` (below) |

```python
    def _send(self, data: bytes):
        with self._send_lock:                       # check and send as one step, so panic() can't slip in between
            if self._panicked and data != _BLACKOUT:
                return                              # after panic(): nothing but dark frames, until start()
            self._sequence = next_sequence(self._sequence)
            self._sender.send(build_artdmx(data, self.port, self._sequence))
        if self.active:                             # outside the lock: may emit signals and log
            self._update_status()
```

```python
    def panic(self):
        """Emergency blackout, from any thread (the exception hook calls it).
        First stops every later show frame (only dark frames go out until the
        next start()); then, if the output may be lit, sends the blackout
        BLACKOUT_REPEATS times straight through the socket; then queues stop()
        on this object's thread (it blacks out once more and stops the timer:
        on the GUI thread's next event-loop pass, even if that thread is the
        one that raised). Uses only Python state before the sends, so it works
        at exit after the window and its Qt objects are gone. Never raises."""
        try:
            self._panicked = True                          # first: from here on _send() lets only dark frames out
            if self._closed:
                log.debug('DMX: emergency stop: output closed, nothing to black out')
                return
            if self.state == 'off':                        # never sent, or stop() already blacked out (M5)
                log.debug('DMX: emergency stop: not sending, nothing to black out')
            else:
                self._send_blackout_now()
            try:
                self._stop_requested.emit()                # always, so a start() racing with this one is stopped too
            except RuntimeError:                           # the Qt object is gone (at exit): nothing left to stop
                log.debug('DMX: emergency stop: Qt object gone, stop() not queued')
        except BaseException:
            log.exception('DMX: emergency stop failed')

    def _send_blackout_now(self):
        """panic()'s blackout: BLACKOUT_REPEATS dark frames under the send lock.
        Logs only after the lock is released."""
        locked = self._send_lock.acquire(timeout=_PANIC_LOCK_TIMEOUT_S)
        errors = []
        try:
            sender, port = self._sender, self.port         # one read each: configure() may swap them
            for _ in range(BLACKOUT_REPEATS):
                try:
                    self._sequence = next_sequence(self._sequence)
                    sender.send(build_artdmx(_BLACKOUT, port, self._sequence))
                except Exception as e:
                    errors.append(e)
        finally:
            if locked:
                self._send_lock.release()
        if not locked:
            log.warning('DMX: emergency blackout sent without the send lock (a send seemed stuck)')
        for e in errors:
            log.error(f'DMX: emergency blackout frame not sent: {e!r}')
        log.warning(f'DMX: emergency blackout sent ({BLACKOUT_REPEATS - len(errors)} of {BLACKOUT_REPEATS} frames)',
                    extra={'tone': Tone.OFF})
```

`panic()` doesn't go through `_send()`. `_send()` calls `self.active` and `_update_status()`, which are Qt calls and
GUI-thread state, and it would block on the lock that `panic()` already holds.

### 3.4 `src/pylzr/midi/midi_output.py`

| Lines | Change |
|---|---|
| `:1` | add `import threading` (stdlib block above `import rtmidi as midi`) |
| after `:15` | constants below |
| `:18-31` docstring | add: "panic() is the emergency stop: all notes off, then optionally a note, from any thread (sends are serialised by a lock, since rtmidi doesn't promise thread safety)." |
| `:33-43` `__init__` | add `self._send_lock = threading.Lock()   # press_note (GUI thread) vs panic() (any thread)` |
| `:81-88` `close()` | wrap `self.midiout.close_port()` in `with self._send_lock:` so panic() never sends on a port being closed |
| `:90-104` `press_note` | delete the local `NOTE_ON`/`NOTE_OFF` (`:94-95`) and use the module constants; wrap both `send_message` calls in `with self._send_lock:`; change the comment at `:103` to "Runs on this (GUI) thread's event loop; panic() may send from another thread, hence the lock" |
| new method after `:104` | `panic()`, below |

```python
_NOTE_ON        = 0x90    # channel 1, the only channel PyLZR sends on
_NOTE_OFF       = 0x80
_CONTROL_CHANGE = 0xB0
_ALL_NOTES_OFF  = 123     # controller 123, value 0: release every sounding note on the channel
_VELOCITY       = 112
_PANIC_LOCK_TIMEOUT_S = 0.1   # don't wait longer than this on a send stuck in the driver
```

```python
    def panic(self, note: int | None = None) -> bool:
        """Emergency stop, from any thread: all notes off (channel 1), then
        `note` if given (Note ON, then at once its Note OFF). The note comes
        last, so nothing sent here releases it afterwards. Does nothing while
        no port is open. Never raises: a failed send is logged and the
        remaining messages are still tried. Returns True if `note`'s Note ON
        was sent."""
        note_sent = False
        try:
            out = self.midiout                               # one read: close() may clear it meanwhile
            if out is None:
                log.debug('MIDI: emergency stop: no port open, nothing sent')
                return False
            messages = [[_CONTROL_CHANGE, _ALL_NOTES_OFF, 0]]
            if note is not None:
                messages += [[_NOTE_ON, note, _VELOCITY], [_NOTE_OFF, note, 0]]
            if not self._send_lock.acquire(timeout=_PANIC_LOCK_TIMEOUT_S):
                log.error('MIDI: emergency stop not sent: another MIDI send is stuck')
                return False
            try:
                for message in messages:
                    try:
                        out.send_message(message)
                        note_sent = note_sent or message[0] == _NOTE_ON
                    except Exception as e:
                        log.error(f'MIDI: emergency stop message {message} not sent: {e}')
            finally:
                self._send_lock.release()
            then = f', then note {note}' if note_sent else ''
            log.warning(f'MIDI: emergency stop sent (all notes off{then})')
        except BaseException:
            log.exception('MIDI: emergency stop failed')
        return note_sent
```

**Order (Q2).** All-notes-off goes first, then SPACE ON, then SPACE OFF. Today every key press sends ON and then OFF
50 ms later, and SoundSwitch keeps the look after the OFF, so a release doesn't end a look. Sent *after* SPACE,
all-notes-off would release SPACE too. That is probably harmless for the same reason, but nobody has checked how
SoundSwitch handles controller 123, so it goes first and SPACE is the last thing SoundSwitch receives. The OFF is
sent at once (not after 50 ms): the stop may run off the GUI thread or with no event loop (at exit), and a `QTimer`
can't be used there. A Note OFF still pending from a key pressed just before the stop can arrive after SPACE. It's
an OFF for a different note, the same as happens today, so it's harmless. Whether SPACE latches or toggles no longer
matters for safety: per Q10, SPACE reaches SoundSwitch at most once per MIDI enable (§3.6).

### 3.5 `src/pylzr/midi/key_map.py` and `src/pylzr/midi/__init__.py`

- `key_map.py`, after `:32`:
  ```python
  # SPACE's note (106). SoundSwitch's blackout look is mapped to it; the emergency stop sends it in MIDI mode.
  BLACKOUT_NOTE = _KEY_TO_NOTE[int(Qt.Key_Space)][0]
  ```
- `midi/__init__.py:1-4`: `from .key_map import BLACKOUT_NOTE, KeyboardMapper`; `__all__ = ['MIDIOutput', 'KeyboardMapper', 'BLACKOUT_NOTE']`.

### 3.6 `src/pylzr/gui/main_window.py`

| Lines | Change |
|---|---|
| `:1` | add `import threading` |
| after `:10` | `from ..core.safety import EmergencyStop` |
| `:12` | `from ..midi     import BLACKOUT_NOTE, MIDIOutput, KeyboardMapper` |
| `:26-42` docstring | add before "This class only connects things": "On an unhandled exception the emergency stop (`safety`, made by main()) blacks out DMX and, in MIDI mode, sends all notes off and, once per MIDI enable, SoundSwitch's blackout note; the window keeps running with DMX stopped (docs/design/safety-phase.md)." |
| `:44` | `def __init__(self, safety: EmergencyStop | None = None):`. None (tests) means a private `EmergencyStop` with no hook, so the stops are still registered and can be triggered directly. |
| after `:65` (`self.output = …`), before the engine | snippet A. It must come before `_apply_settings` (`:135`), which can start DMX from saved settings. |
| `_on_control_mode_changed` `:261-272`, after `self.output.select(mode)` | snippet B (re-arm) |
| new section before `# Qt event overrides` (`:352`) | `# Emergency stop` + `_midi_emergency_stop` (snippet C) |
| `closeEvent` `:371-382`, after `self.dmx_out.close()` (`:380`) | `self.safety.unregister('dmx')` and `self.safety.unregister('midi')`. They go last, so an exception earlier in `closeEvent` still reaches registered stops. `closeEvent` is safe to run twice (Ctrl+C during a close, test teardown): every call in it is idempotent. |

A:
```python
        # Emergency stop: on an unhandled exception, DMX goes dark first, then SoundSwitch gets all notes off and,
        # once per MIDI enable, its blackout note (design Q2, Q10)
        self._space_lock  = threading.Lock()     # guards _space_armed; the stop may run on any thread
        self._space_armed = True
        self.safety = safety if safety is not None else EmergencyStop()
        self.safety.register('dmx', self.dmx_out.panic)
        self.safety.register('midi', self._midi_emergency_stop)
```
B:
```python
        if mode == 'MIDI':
            with self._space_lock:
                self._space_armed = True          # MIDI (re)enabled: the next emergency stop sends SPACE again (Q10)
```
C:
```python
    # ------------------------------------------------------------------
    # Emergency stop
    # ------------------------------------------------------------------

    def _midi_emergency_stop(self):
        """In MIDI mode: all notes off, and, the first time since MIDI was
        (re)enabled, SPACE too (SoundSwitch's blackout look). Never twice,
        since SoundSwitch might toggle on it (design Q10). Any thread; reads
        only Python state; never raises."""
        if self.output.active != 'MIDI':
            return
        with self._space_lock:
            space, self._space_armed = self._space_armed, False
        sent = self.midi_out.panic(BLACKOUT_NOTE if space else None)
        if space and not sent:                   # SPACE never reached the port: still due (ASSUMPTION Q11)
            with self._space_lock:
                self._space_armed = True
```

The test-and-clear under `_space_lock` means two stops on two threads at once send SPACE once between them. The lock
is held only for the swap (no calls out), so it can't deadlock or delay anything. The mode is checked when the stop
runs, not by registering and unregistering on each mode switch. That gives one registration and no state to keep in
step with `_on_control_mode_changed`. `OutputSwitch.active` is a plain `str` attribute, so reading it from another
thread is safe.

Under Q1 the dropdown and `output.active` stay on DMX after the stop. Choosing MIDI calls `dmx_out.stop()` (a no-op,
already stopped), closes the tester and re-arms SPACE; choosing DMX again calls `dmx_out.start()`, which clears
`_panicked`.

### 3.7 `tests/conftest.py:101-111` (`make_window`)

`def factory(**kwargs) -> WindowHarness:` → `WindowHarness(MainWindow(**kwargs))`. Existing callers pass nothing, so
none of them change.

---

## 4. New and changed names

| Name | Where | Signature / value |
|---|---|---|
| `EmergencyStop` | `core/safety.py` | `register(name: str, stop: Callable[[], None]) -> None`, `unregister(name: str) -> None`, `trigger(reason: str) -> None`, `triggered: bool` (property) |
| `install_excepthook` | `core/safety.py` | `(stop: EmergencyStop, on_handled: Callable[[], None] \| None = None, on_interrupt: Callable[[], None] \| None = None) -> None` |
| `_ExceptionHandler` | `core/safety.py` (private) | `handle(exc_type, exc_value, exc_tb, thread_name=None)`, `handle_thread(args)` |
| `log` | `core/safety.py` | logger `'pylzr.safety'` |
| `KEEP_RUNNING_HINT`, `_quit_as_if_closed` | `__main__.py` | the Q1 hint string; the Q8 quit (queues `QApplication.closeAllWindows`) |
| `DMXOutput.panic`, `DMXOutput._send_blackout_now` | `dmx/dmx_output.py` | `() -> None` |
| `DMXOutput._stop_requested` | `dmx/dmx_output.py` | `pyqtSignal()`, connected `QueuedConnection` to `stop` |
| `DMXOutput._send_lock`, `DMXOutput._panicked` | `dmx/dmx_output.py` | `threading.Lock()`, `bool` (False until `panic()`, cleared by `start()`) |
| `_PANIC_LOCK_TIMEOUT_S` | `dmx/dmx_output.py` | `0.005` |
| `MIDIOutput.panic` | `midi/midi_output.py` | `(note: int \| None = None) -> bool` (True if the note's ON was sent) |
| `MIDIOutput._send_lock` | `midi/midi_output.py` | `threading.Lock()` |
| `_NOTE_ON`, `_NOTE_OFF`, `_CONTROL_CHANGE`, `_ALL_NOTES_OFF`, `_VELOCITY`, `_PANIC_LOCK_TIMEOUT_S` | `midi/midi_output.py` | `0x90`, `0x80`, `0xB0`, `123`, `112`, `0.1` |
| `BLACKOUT_NOTE` | `midi/key_map.py`, exported by `pylzr.midi` | `106` (SPACE) |
| `MainWindow.__init__` | `gui/main_window.py` | `(safety: EmergencyStop \| None = None)`; attributes `safety`, `_space_lock`, `_space_armed` |
| `MainWindow._midi_emergency_stop` | `gui/main_window.py` | `() -> None` |
| Stop names | registrations | `'dmx'` (first), `'midi'` (second) |
| Trigger reasons | callers | `'unhandled exception'`, `'interrupted'` (hook), `'exit'` (atexit) |

---

## 5. Threading

| Piece | Runs on | Notes |
|---|---|---|
| `sys.excepthook` handler | the thread that raised: `MainThread` for GUI slots, the FFT `QThread` (Python sees it as `Dummy-N`) for `FFTWorker.process`, the main thread for a top-level exception | Checked with PyQt 5.15.11 / Qt 5.15.2 in a scratch script: with a replaced hook, a raising slot on either thread calls the hook on that thread, the process stays up, and the worker thread keeps processing later queued calls. |
| `threading.excepthook` handler | the raising Python thread | `SystemExit` ignored, as by default |
| `KeyboardInterrupt` | always the main (GUI) thread: Python runs signal handlers there only | `on_interrupt` queues `closeAllWindows` with `QTimer.singleShot(0, …)` on that thread's event loop |
| `EmergencyStop.trigger` | the caller's thread; at exit, the main thread during interpreter shutdown (no event loop) | No cross-thread waiting; per-thread re-entry guard. `_lock` is held only to copy the dict. |
| `DMXOutput.panic` | caller's thread | Sets `_panicked`, sends under `_send_lock`, emits `_stop_requested` |
| `DMXOutput._send` (every show frame, `stop()`'s and `configure()`'s blackouts) | GUI thread | Flag check + send under `_send_lock` |
| queued `DMXOutput.stop()` | `dmx_out`'s thread (GUI), next event-loop pass | Same thread even when the GUI thread raised: the event is posted, not called directly. At exit nothing runs it (no event loop), which is fine because the dark frames already went out. |
| `MainWindow._midi_emergency_stop` → `MIDIOutput.panic` | caller's thread | SPACE arm swapped under `_space_lock`; sends under `MIDIOutput._send_lock` (≤ 0.1 s wait). `press_note`, the delayed OFF (GUI thread) and `close()` take the same send lock. |
| `on_handled` (hint) | raising thread, once | Logging only. The log panel's handler hands records to the GUI thread through its `_Bridge` signal (`log_panel.py:30-46`), so logging from the FFT thread is safe. |
| `atexit` trigger | main thread, after `app.exec_()` returns and `sys.exit` raises | Registered after the `PyQt5` import, so it runs before PyQt's own exit cleanup (atexit runs last-in, first-out). `panic()` doesn't rely on Qt being alive (M5). |

**Why M2 needs a lock, and why it's safe within the frame deadline.**
- *A flag alone can't close the gap.* The GUI thread can read `_panicked` (False) and then lose the GIL before its
  `sendto`. `panic()` then sets the flag and sends its dark frames, and the GUI thread resumes and sends the show
  frame after them. The check and the send must be one step relative to `panic()`. That takes a lock, or a spin-wait,
  which is a lock by another name.
- *Setting the flag before taking the lock gives the ordering.* Any `_send()` that takes the lock after the flag is
  set sees it and sends nothing lit. A `_send()` that already holds the lock finishes first, so its frame goes out
  *before* the first dark frame. So no show frame can follow the first dark frame.
- *What runs under the lock:* the flag check, one sequence increment, `build_artdmx` (a ~530-byte concatenation), and
  `sendto` on a non-blocking socket (it never waits: a full buffer raises `BlockingIOError` and the datagram is
  dropped). That's one frame for the GUI thread and three for `panic()`, tens of microseconds either way, well inside
  the 25 ms frame interval. Uncontended, taking the lock costs about 0.1 µs per frame, 40 times a second.
- *Why it can't deadlock.* No Qt call, signal emit, logging or other callback runs under the lock. Status updates
  and logging happen after release. So nothing inside can raise into the hook and re-enter `panic()` on the same
  thread. A `KeyboardInterrupt` landing inside is released by `with`. As a backstop, `panic()` waits at most
  `_PANIC_LOCK_TIMEOUT_S` (5 ms). If that ever expires, it sends without the lock and logs a warning: the blackout
  isn't delayed, and later show frames are still blocked by the flag.
- The same lock removes the M6 races: sequence numbers stay unique, and `last_error`/`dropped` have one writer at a
  time.

Deadline: the stop runs before any logging (M3), and the three datagrams go back to back, so dark frames leave within
microseconds of the hook starting (plus at most one in-flight GUI frame). The 25 ms budget holds as long as the GUI
thread isn't stuck. If it is stuck, the hook isn't running there anyway.

---

## 6. Edge cases

| Case | Handling |
|---|---|
| DMX off (MIDI mode) | `panic()`: flag set, `state == 'off'` → DEBUG line, nothing sent; queued `stop()` is a no-op. The flag is cleared by the next `start()`. |
| DMX closed (after `closeEvent`) | `panic()`: `_closed` → nothing. Also, `closeEvent` has already unregistered both stops. |
| `panic()` after the Qt object is deleted (exit) | Python attributes still readable; frames sent; the `emit` raises `RuntimeError`, which `panic()` catches and logs at DEBUG |
| GUI tick while `panic()` holds the lock (FFT case) | waits µs, then sees the flag: nothing sent |
| GUI frame in flight when `panic()` starts | goes out before the first dark frame (the lock orders them) |
| `configure()` between `panic()` and the queued `stop()` | old node: `configure()`'s own blackout (dark: allowed); new node: its `_tick()` is blocked by the flag; the queued `stop()` blacks out the new node |
| `start()` racing with a `panic()` on another thread | the flag blocks every show frame; `panic()` always queues `stop()`, which then stops the new run (dark). The user switches Control Mode again to resume. |
| User re-enables DMX (MIDI → DMX) | `start()` clears `_panicked` (INFO line) and sends the show at once |
| A send fails (`OSError`) | `UdpSender` returns False and sets `last_error`; the other copies still go out |
| A send raises (`RuntimeError`: sender closed by a concurrent `configure()`) | collected and logged after the lock is released; the queued `stop()` blacks out the new node |
| `panic()` can't get the lock within 5 ms (shouldn't happen) | sends anyway, WARNING logged |
| Queued `stop()` itself raises | hook → trigger → `panic()` (state not `'off'`) → dark frames → stop queued again. Keeps the laser dark, once per event-loop pass; logging is bounded by Q7. Accepted. |
| MIDI port not open | `MIDIOutput.panic()` returns False, DEBUG line; SPACE stays armed (Q11) |
| MIDI send raises (`RtMidiError`, driver error, port closed underneath) | caught per message, ERROR; remaining messages still tried; `panic()` returns whether SPACE's ON went out (if not, it stays armed) |
| MIDI send stuck in the driver on another thread | `acquire(timeout=0.1)` fails → ERROR, returns False. DMX already ran first. |
| `close()` / `open()` on the GUI thread during a MIDI panic on the FFT thread | `close_port()` waits for the lock; `panic()` used its own `out` reference |
| Second and later stops in MIDI mode | all-notes-off only (Q10), until Control Mode is switched to MIDI again |
| Two stops at once on two threads, MIDI mode | `_space_lock` test-and-clear: SPACE once; all-notes-off twice |
| DMX mode | `'midi'` stop does nothing (`output.active != 'MIDI'`) and doesn't use up the SPACE arm |
| Stop callable raises inside `trigger()` | `log.exception`, the rest still run, `triggered` stays True |
| `trigger()` from inside a stop (same thread) | returns at once |
| Same error on every frame (FFT bug: ~43/s) | stop runs every time (DMX: DEBUG once off; MIDI: all-notes-off each time, SPACE once); log: full traceback once, then one line at 2, 4, 8, … (Q7) |
| Log panel's own slot raises on every record | the loop dies out: the 3rd identical error isn't logged, so no new record reaches the panel |
| Exception before any stop is registered (in `QApplication()`, `style.apply`) | trigger logs DEBUG "nothing registered"; traceback logged to the console (M4) |
| Exception escaping `MainWindow.__init__` after saved settings started DMX | stops registered at `:65+`, before `_apply_settings`; top-level hook → blackout; then `atexit` → `panic()` again (`state` not `'off'`; Qt objects possibly gone, M5) |
| Exception inside `closeEvent` after `dmx_out.stop()` | stops still registered (unregistered last); DMX already off. The rest of `closeEvent` is skipped, as today; out of scope. |
| Ctrl+C in a slot | stop, one WARNING line (no traceback, no hint), `closeAllWindows` queued → `closeEvent` → app quits (Q8) |
| Ctrl+C twice | the second queued `closeAllWindows` finds no visible window: no-op |
| Ctrl+C during `closeEvent` | the stop runs; the queued close skips a window that's already closing; whatever `closeEvent` hadn't done yet is skipped, as for any exception there (out of scope) |
| Ctrl+C during startup (before `exec_()`) | raised in `main()` → top-level hook → stop + WARNING; the process exits (the queued close never runs) |
| `SystemExit` in a Python thread | ignored, as by default |
| The hook itself fails (e.g. `on_handled` raises) | `_last_resort` prints the original and the hook's own traceback to stderr, if there is one. The hook never raises, so PyQt never falls back to `qFatal`. |
| No console (`pythonw`) | console handler not added (`app_logger.py:86-88`); the log panel shows it once the window exists; earlier failures go unlogged, as today |
| Hint line on a startup failure | `on_handled` logs "keeps running" just before the process exits. One misleading line; accepted. |
| Exceptions in `__del__` / weakref callbacks (`sys.unraisablehook`) | not hooked; they don't abort today either. Out of scope. |
| Tester open when the stop happens | stays open (Q1: nothing touched); its values don't go out while DMX is stopped |

---

## 7. Tests

### 7.1 Existing tests that change

- `tests/conftest.py:101-111`: `make_window`'s factory takes `**kwargs` (3.7). No assertion changes.
- No existing assertion changes. `press_note` sends the same messages. `stop()`, `close()` and `configure()` send the
  same frames, since `_send()` behaves as before while `_panicked` is False. Nothing checks `pylzr.midi.__all__`.
  `test_closing_in_midi_mode_sends_no_dmx` still holds: closing doesn't trigger the stop.

### 7.2 New tests: `tests/test_key_map.py` (append after `:56`)

- `test_blackout_note_is_space`: `BLACKOUT_NOTE == 106`, and `make_mapper()` + `handle_key(int(Qt.Key_Space))` sends
  `[BLACKOUT_NOTE]`.

### 7.3 New tests: `tests/test_midi_output.py` (append after `:105`)

ALL_OFF = `[0xB0, 123, 0]`.
1. `test_panic_sends_all_notes_off_then_the_note_on_and_off(os_name)`: with `'PyLZR-MIDI 1'` added and connected,
   `m.panic(106) is True` and `fake_rtmidi.sent == [(port, ALL_OFF), (port, [0x90, 106, 112]), (port, [0x80, 106, 0])]`,
   immediately (no event loop needed).
2. `test_panic_without_a_note_sends_only_all_notes_off`: returns False; `[ALL_OFF]`.
3. `test_panic_while_disconnected_sends_nothing`: `reset('win')`, `panic(106) is False`, `sent == []`.
4. `test_panic_keeps_going_when_a_send_fails(monkeypatch, caplog)`: `m.midiout.send_message` raises
   `fake_rtmidi.RtMidiError` on the first call only → returns True; the ON/OFF pair still sent; one ERROR record
   mentions `[176, 123, 0]`.
5. `test_panic_returns_false_when_the_note_on_fails(monkeypatch)`: `send_message` raises for `0x90` only → False.
6. `test_panic_on_a_port_closed_underneath_does_not_raise`: `m.midiout.close_port()` directly, then `panic(106)` →
   False, no exception (the fake raises `InvalidUseError`), ERROR logged.
7. `test_panic_from_another_thread`: `threading.Thread(target=m.panic, args=(106,))`, start and join → the three
   messages are in `fake_rtmidi.sent`.
8. `test_a_pending_note_off_still_arrives_after_panic`: `press_note(64)`, `panic(106)`, `wait_for_note_offs()` →
   messages in order `[ON 64, ALL_OFF, ON 106, OFF 106, OFF 64]`.

### 7.4 New tests: `tests/test_dmx_output.py` (new section `# ── Emergency stop ──` after `:173`)

Imports: `threading`, `time`, `from PyQt5 import sip`. Request `out` **before** `monkeypatch` in signatures, so
monkeypatch is undone before the fixture's `close()`. `SHOW = bytes([255]) + bytes(511)`.
1. `test_panic_blacks_out_at_once_and_stops_on_the_next_event_pass(out, qapp)`: `universe.set(1, 255)`, `start()`,
   `panic()` → `len(packets()) == 1 + 3`, `frames()[1:] == DARK`, `out.active` still True;
   `qapp.processEvents()` → `not out.active`, `len(packets()) == 1 + 6`, `frames()[-3:] == DARK`,
   `out.state == 'off'`; `out.universe.get(1) == 255` (the show is kept).
2. `test_after_panic_only_dark_frames_go_out_until_start(out, qapp)` (M2): `universe.set(1, 255)`, `start()`,
   `panic()`; `out._tick()` twice → no new packets; `out.configure('10.201.6.101', PortAddress())` → every packet
   after the first is dark (old node's blackout only, nothing to the new node); `processEvents()` → stopped;
   `start()` → `frames()[-1] == SHOW`.
3. `test_frames_sent_during_a_panic_on_another_thread_are_dark(out, monkeypatch)` (M2 race): `universe.set(1, 255)`,
   `start()`. Wrap `FakeSocket.sendto` to `time.sleep(0.02)` when called off the main thread, so panic holds the lock
   for ~60 ms. Run `out.panic` in a thread; while it's alive, call `out._tick()` every 5 ms on the main thread; join.
   Then, from the first dark frame on, every frame is dark. Without the fix this fails almost every run: the main
   thread's ticks land between the slow dark sends.
4. `test_panic_while_stopped_sends_nothing(out, qapp, caplog)`: `panic()`, `processEvents()` → `sent == []`, not
   active; DEBUG "nothing to black out"; `start()` afterwards sends the show (flag cleared).
5. `test_panic_after_close_sends_nothing(out)`: `start()`, `close()`, `n = len(sent)`, `panic()` → `len(sent) == n`.
6. `test_each_panic_copy_has_its_own_sequence_number(out)`: `start()`, `panic()` → sequences `[1, 2, 3, 4]`.
7. `test_panic_never_raises(out, monkeypatch, caplog)`: `start()`; `monkeypatch.setattr(out._sender, 'send', raiser)`
   with `raiser` raising `RuntimeError` → `panic()` returns; 3 ERROR records "frame not sent".
8. `test_panic_from_another_thread(out)`: `start()`; run `out.panic` in a `threading.Thread`, join → 3 dark frames
   after the first; `wait_until(lambda: not out.active)` (the queued stop reached the GUI thread).
9. `test_panic_after_the_qt_object_is_gone_still_blacks_out()`: a local `DMXOutput(socket_factory=FakeSocket)` (not
   the fixture), `start()`, `sip.delete(o)`, `o.panic()` → no exception, `frames()[-3:] == DARK`.

### 7.5 New tests: `tests/test_safety.py` (new file)

Fixtures:
```python
@pytest.fixture
def hooks(monkeypatch):
    """sys/threading excepthooks are put back after the test (pytest 9 installs its own threading hook per session)."""
    monkeypatch.setattr(sys, 'excepthook', sys.excepthook)
    monkeypatch.setattr(threading, 'excepthook', threading.excepthook)

@pytest.fixture
def safety(hooks) -> EmergencyStop:
    stop = EmergencyStop()
    install_excepthook(stop)
    return stop
```
Helper `raise_in_a_slot(exc=RuntimeError('boom'))`: a `QObject` with `fire = pyqtSignal()`, connected to a function
raising `exc`, emitted on the GUI thread. It first asserts `sys.excepthook is not sys.__excepthook__`; otherwise PyQt
calls `qFatal` and the whole pytest run aborts. `unhandled(caplog)` = the records with `exc_info`. `SPACE_ON =
[0x90, 106, 112]`, `SPACE_OFF = [0x80, 106, 0]`, `ALL_OFF = [0xB0, 123, 0]`.

**EmergencyStop**
1. `test_trigger_with_nothing_registered_is_harmless`: `triggered` False → `trigger('x')` → True; DEBUG "nothing
   registered".
2. `test_trigger_runs_every_stop_in_registration_order`: three recorders → `['a', 'b', 'c']`.
3. `test_registering_a_name_again_replaces_it_in_place`: register a, b, then a again (new callable) → order
   `[a2, b]`.
4. `test_unregister_removes_a_stop_and_ignores_unknown_names`.
5. `test_a_stop_that_raises_is_logged_and_the_rest_still_run(caplog)`: middle stop raises → the others ran;
   `trigger` didn't raise; one ERROR record naming the stop; `triggered` True.
6. `test_trigger_twice_runs_every_stop_twice`.
7. `test_trigger_from_inside_a_stop_is_ignored`: a stop calls `stop.trigger('again')` → each stop ran once.
8. `test_trigger_from_another_thread_runs_the_stops_there`: recorded thread name is the worker's.
9. `test_stops_run_before_the_summary_is_logged(caplog)`: a stop logs "stop ran"; record order is the stop's line,
   then "Emergency stop (x): …".

**The hook**
10. `test_install_replaces_both_hooks(hooks)`.
11. `test_unhandled_exception_stops_first_then_logs_the_traceback_once(safety, caplog)`: a stop records
    `len(caplog.records)` when it runs; `try: raise RuntimeError('boom') except: sys.excepthook(*sys.exc_info())` →
    the stop saw no ERROR record yet; exactly one record with `exc_info[0] is RuntimeError` on logger `pylzr.safety`.
12. `test_a_repeating_error_logs_at_1_2_4_8_and_stops_every_time(safety, caplog)`: the same `raise` site handled 10×
    → the stop ran 10×; one record with `exc_info`, plus 3 "same error again" records with counts 2, 4, 8.
13. `test_different_errors_each_get_their_traceback`: two raise sites → two `exc_info` records.
14. `test_on_handled_runs_once_after_the_first_error(hooks)`: install with a counter; handle 3 errors → 1.
15. `test_exception_in_a_python_thread_is_handled(safety, caplog)`: real `threading.Thread` that raises; join →
    stop ran; the record's message names the thread.
16. `test_systemexit_in_a_thread_is_ignored(safety)`: thread calls `sys.exit()` → stop not run, nothing logged.
17. `test_ctrl_c_stops_then_asks_to_quit(hooks, caplog)`: install with `on_handled` and `on_interrupt` counters;
    handle a `KeyboardInterrupt` → stop ran (reason `'interrupted'`); one WARNING "Interrupted (Ctrl+C)", no
    `exc_info`; `on_interrupt` called once; `on_handled` not called.
18. `test_the_hook_never_raises(hooks, capsys)`: `on_handled` raises → `sys.excepthook(...)` returns; stderr has both
    tracebacks.
19. `test_safety_module_imports_no_qt`: parse `src/pylzr/core/safety.py` with `ast` → no import starting with
    `PyQt5`.

**In the app** (window: `make_window(safety=safety)`; `frames()` = `[p['data'] for p in dmx_packets()]`)

20. `test_exception_in_a_gui_slot_blacks_out_and_the_app_keeps_running(safety, make_window, qapp, caplog)`: DMX mode,
    `universe.set(1, 255)`, `n = len(dmx_packets())`, `raise_in_a_slot()` → `frames()[n:] == DARK` (before any event
    processing); `processEvents()` → `not dmx_out.active`, `frames()[-3:] == DARK`, indicator text `'Off'`,
    `output.active == 'DMX'` and `_mode_combo.currentData() == 'DMX'` (Q1); `len(unhandled(caplog)) == 1`; the log
    panel text contains `'RuntimeError: boom'` exactly once; a key press still works.
21. `test_switching_control_mode_after_the_stop_resumes_dmx`: after 20's steps, `set_mode('MIDI')`,
    `set_mode('DMX')` → `dmx_out.active`, `frames()[-1][0] == 255`.
22. `test_exception_in_the_fft_thread_blacks_out_and_analysis_continues(safety, make_window, monkeypatch, caplog)`:
    *before* `make_window`, `monkeypatch.setattr(FFTWorker, 'process', wrapper)`, where `wrapper` is
    `@pyqtSlot(np.ndarray)`, raises `RuntimeError('fft boom')` on its first call and calls the original after. DMX
    mode; deliver one chunk with `fake_pyaudio.deliver(..., stream=w.engine.audio._stream)`;
    `wait_until(lambda: not w.dmx_out.active)` → `frames()[-3:] == DARK`; exactly one `exc_info` record, with
    `threadName != 'MainThread'`; then `harness.feed(tone_chunks(2, (440, 8000)))` completes (the FFT thread is alive).
23. `test_no_show_frame_follows_the_blackout_when_the_fft_thread_raises(...)` (M2, the requested test): as 22, but
    `universe.set(1, 255)` *before* `set_mode('DMX')`, so every frame before the stop is lit. Slow the FFT thread's
    sends: wrap `FakeSocket.sendto` to `time.sleep(0.02)` off the main thread, so `panic()` spans more than two timer
    ticks while `wait_until` keeps the GUI event loop and the 25 ms timer running. After
    `wait_until(lambda: not w.dmx_out.active)`: `i = first index of a dark frame`; `i > 0` and
    `all(f == bytes(512) for f in frames()[i:])`.
24. `test_midi_mode_stop_sends_all_notes_off_then_space_and_keeps_running(safety, make_window)`: default (mac,
    virtual port open) → `raise_in_a_slot()` → `note_messages() == [ALL_OFF, SPACE_ON, SPACE_OFF]`;
    `dmx_packets() == []`; then `harness.key(Qt.Key_Q)` and `wait_for_note_offs()` → `[73, 112]` was sent.
25. `test_later_stops_send_all_notes_off_only(make_window)`: `w.safety.trigger('t')` three times →
    `note_messages() == [ALL_OFF, SPACE_ON, SPACE_OFF, ALL_OFF, ALL_OFF]` (Q10).
26. `test_switching_control_mode_to_midi_rearms_space(make_window)`: trigger; `set_mode('DMX')`; `set_mode('MIDI')`;
    trigger → `note_ons() == [[106, 112], [106, 112]]`.
27. `test_space_stays_armed_until_it_reaches_the_port(make_window)` (Q11): `fake_rtmidi.reset('win')` before
    `make_window` (no port) → trigger → `fake_rtmidi.sent == []`, `fake_udp.sent == []`; then
    `fake_rtmidi.ports.append('PyLZR-MIDI 1')`, `w.midi_out.open('PyLZR-MIDI 1')`, trigger →
    `[ALL_OFF, SPACE_ON, SPACE_OFF]`.
28. `test_two_stops_at_once_send_space_once(make_window)`: two threads behind a `threading.Barrier(2)` each call
    `w.safety.trigger('t')` → exactly one `SPACE_ON` and two `ALL_OFF` in `note_messages()`.
29. `test_dmx_mode_stop_sends_no_midi_and_keeps_space_armed`: DMX mode, trigger → `note_messages() == []`. Then
    `w.output.select('MIDI')` directly (bypassing `_on_control_mode_changed`, so nothing re-arms), trigger →
    `[ALL_OFF, SPACE_ON, SPACE_OFF]`: the DMX-mode stop didn't use up the arm.
30. `test_trigger_twice_sends_the_blackout_once_per_call(make_window, qapp)`: DMX mode, `n`; `trigger` → `n + 3`;
    `trigger` → `n + 6` (no events processed in between); `processEvents()` → `n + 9`, not active; `trigger` again →
    nothing new (DMX is off now).
31. `test_closing_the_window_unregisters_its_stops`: `h.close()`; counts of `fake_udp.sent` / `fake_rtmidi.sent`;
    `w.safety.trigger('x')` → unchanged, no exception.
32. `test_ctrl_c_in_a_slot_closes_the_window_like_the_close_button(hooks, make_window, qapp)` (Q8):
    `stop = EmergencyStop()`;
    `install_excepthook(stop, on_interrupt=pylzr.__main__._quit_as_if_closed)`; `h = make_window(safety=stop)`;
    `w.show()`; DMX mode, `universe.set(1, 255)`; `raise_in_a_slot(KeyboardInterrupt())`;
    `wait_until(lambda: not w.isVisible())` → `w.engine._is_shut_down`, `fake_udp.sockets[0].closed == 1`,
    `frames()[-3:] == DARK`, and the stops are unregistered (closeEvent ran).
33. `test_atexit_blacks_out[alive|qt_object_deleted]`: subprocess
    (`[sys.executable, '-c', code]`, `env` with `PYTHONPATH=src` + `tests` joined by `os.pathsep`,
    `QT_QPA_PLATFORM=offscreen`, `timeout=30`). The script: `atexit.register(report)` first (so it runs last),
    `QCoreApplication([])`, `DMXOutput(socket_factory=fake_udp.FakeSocket)`, `universe.set(1, 255)`, `start()`,
    `EmergencyStop()`, `register('dmx', out.panic)`, `atexit.register(stop.trigger, 'exit')`, `sip.delete(out)` in the
    `qt_object_deleted` case, `sys.exit(0)`. `report` prints how many ArtDmx packets after the first are
    `bytes(512)`. Assert returncode 0 and stdout `dark 3`.
34. `test_main_installs_the_hook_and_atexit_before_any_qt_object(monkeypatch, qapp, caplog)`: monkeypatch
    `pylzr.__main__.configure_console_logging`, `.install_excepthook` and `.QApplication` (stub: `exec_()` returns 0),
    `atexit.register`, `pylzr.gui.style.apply` and `pylzr.gui.MainWindow` (stub recording `safety`) with recorders
    → `pytest.raises(SystemExit)`; event order `console, hook, atexit, app, window`; the same `EmergencyStop` in hook,
    atexit (`fn == stop.trigger`, `args == ('exit',)`) and window; `on_interrupt is _quit_as_if_closed`; calling the
    captured `on_handled` logs `KEEP_RUNNING_HINT`.
35. `test_quit_as_if_closed_queues_close_all_windows(monkeypatch, qapp)`: monkeypatch `pylzr.__main__.QTimer` with a
    stub recording `singleShot(ms, fn)` → `_quit_as_if_closed()` records `(0, QApplication.closeAllWindows)`.

Expected count after the task: 1318 + 1 (7.2) + 9 (7.3: 8, the first run on two OSes) + 9 (7.4) + 36 (7.5: 35, the
atexit test run twice) = **1373**.

---

## 8. Verification

```powershell
.venv\Scripts\python -m pytest tests/test_key_map.py tests/test_midi_output.py tests/test_dmx_output.py -q
.venv\Scripts\python -m pytest tests/test_safety.py -q
.venv\Scripts\python -m pytest tests/test_main_window_dmx.py tests/test_main_window.py tests/test_engine.py -q
.venv\Scripts\python -m pytest -q                     # 1373 passed, nothing skipped
.venv\Scripts\ruff check .
git diff --exit-code -- tests/golden/                 # golden files unchanged
```

The race tests (7.4 #3, 7.5 #23) must pass every time. Before handing over, run them 20 times in a row:
`for ($i=0; $i -lt 20; $i++) { .venv\Scripts\python -m pytest tests/test_safety.py tests/test_dmx_output.py -q -k "dark or show_frame" }`.
To confirm they'd catch a regression, temporarily remove the flag check in `_send()` and see them fail, then restore
it.

Manual (revert every injected `raise` afterwards; `git diff` must show none):
1. GUI thread, DMX mode: add `raise RuntimeError('test')` at the top of `MainWindow._toggle_settings`; run
   `python -m pylzr`; choose DMX; click the gear. Expect: the window stays open; the console shows "DMX: emergency
   blackout sent", "Emergency stop (unhandled exception): dmx, midi", one traceback, and the hint; the DMX indicator
   (Settings) reads Off while Control Mode still shows DMX; MIDI → DMX resumes sending.
2. FFT thread: in `FFTWorker.process`, raise once (module-level counter); play audio in DMX mode. Same result; the
   spectrum keeps moving afterwards.
3. MIDI mode with loopMIDI + SoundSwitch (or a MIDI monitor): trigger case 1 in MIDI mode twice. Expect CC 123, Note
   ON 106, Note OFF 106 the first time, then CC 123 only. Switch to DMX and back to MIDI, trigger again: SPACE again.
   SoundSwitch goes to its blackout look. *For information only, not a safety dependency (Q10):* press SPACE twice on
   the keyboard and note whether SoundSwitch latches or toggles.
4. Ctrl+C: run `python -m pylzr` from a terminal in DMX mode, press Ctrl+C. Expect "Interrupted (Ctrl+C): outputs
   blacked out; quitting", the window closes, the process exits, and with a node: the laser is dark.
5. With the laser lit (hardware), case 1 in DMX mode: the laser goes dark at once.

---

## 9. Checklist

1. On `hayden/components-pt3` with a clean tree (apart from the docs from this planning step): `pytest -q` →
   1318 passed.
2. `midi/key_map.py`: add `BLACKOUT_NOTE` (3.5); export it from `midi/__init__.py`; add test 7.2. Run
   `pytest tests/test_key_map.py -q`.
3. `midi/midi_output.py`: `import threading`; module constants; `_send_lock` in `__init__`; lock in `close()` and
   `press_note`/`send_off`; delete the local `NOTE_ON`/`NOTE_OFF`; update the `:103` comment and the docstring; add
   `panic()` exactly as in 3.4 (returns `bool`). Add tests 7.3. Run `pytest tests/test_midi_output.py -q`.
4. `dmx/dmx_output.py`: `import threading`; `_PANIC_LOCK_TIMEOUT_S`; docstring edits; `_stop_requested` signal;
   `_send_lock` and `_panicked` in `__init__`; `QueuedConnection`; clear the flag in `start()`; new `_send()`;
   `panic()` and `_send_blackout_now()` exactly as in 3.3, after `close()`. Add tests 7.4. Run
   `pytest tests/test_dmx_output.py -q`, then the race-test loop from §8.
5. Create `core/safety.py` as in 3.1 (`EmergencyStop`, `install_excepthook` with `on_interrupt`,
   `_ExceptionHandler`, `_innermost`, `_last_resort`). Create `tests/test_safety.py` with tests 1–19. Run
   `pytest tests/test_safety.py -q`.
6. `tests/conftest.py`: `make_window` factory takes `**kwargs` (3.7).
7. `gui/main_window.py`: `import threading`, imports, signature, docstring, snippet A after `:65`, snippet B in
   `_on_control_mode_changed`, the `Emergency stop` section with `_midi_emergency_stop` (snippet C), and both
   `unregister` calls at the end of `closeEvent` (3.6). Add tests 20–31. Run
   `pytest tests/test_safety.py tests/test_main_window_dmx.py -q`.
8. `__main__.py`: rewrite as 3.2 (console logging first, `_quit_as_if_closed`). Add tests 32–35.
9. Full suite (1373), `ruff check .`, golden unchanged, race-test loop (§8).
10. Manual checks 1–4 from §8 (5 needs the hardware; note the result for the README's DMX section together with the
    "After task 5" check). Revert every injected `raise`.
11. Mark Task 3 `— DONE` in `PLAN.md`.
12. Stop for review. Commit message:

    ```
    Exception hook and emergency stop (P1)

    An unhandled exception in a slot, on the FFT thread or in a Python thread
    no longer aborts the app: the hook runs the emergency stop first, then
    logs the traceback once. DMX: the blackout goes out at once from any
    thread, no show frame follows it, and the output is then stopped on the
    GUI thread; switching Control Mode re-enables it. MIDI mode: all notes
    off, plus SoundSwitch's blackout note 106 once per MIDI enable. Ctrl+C
    stops, then closes the window as usual. The stop also runs at exit.
    ```
