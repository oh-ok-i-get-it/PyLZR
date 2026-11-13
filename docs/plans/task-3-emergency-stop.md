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
- **Q12** (review follow-up, §10). Opening a MIDI port re-arms SPACE: SoundSwitch on that port hasn't received it
  through this connection.

Review follow-up: §10 lists what changed after the review of `efa64b9`. The sections below already describe the code
after that follow-up.

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
| `:1-3` | add `import itertools` and `import threading` (stdlib block) |
| after `:22` (`BLACKOUT_REPEATS`) | `_PANIC_LOCK_TIMEOUT_S = 0.005   # panic() waits at most this long for a send in progress (one sendto: microseconds)` and `_PANIC_RETRY_TIMEOUT_S = 0.1    # if it gave up, it then waits this long for that send to finish, to black out after it` |
| `:58-89` class docstring | `:62-64` "Everything runs on the GUI thread; one send takes microseconds." → "Everything runs on the GUI thread except panic(), which any thread may call; one send takes microseconds." After `:68` add: "panic() is the emergency stop (docs/design/safety-phase.md): from the moment it starts only dark frames go out, until a start() that comes after a stop(); it sends the blackout BLACKOUT_REPEATS times at once, from whatever thread calls it, then has this object's thread run stop()." |
| after `:91` | `_stop_requested = pyqtSignal()   # from panic(), any thread: stop() runs on this object's thread` |
| after `:107` (`self._closed = False`) | `self._send_lock = threading.Lock()`, then the emergency-stop bookkeeping (below) |
| after `:119` | `self._stop_requested.connect(self.stop, Qt.QueuedConnection)`. It must be queued explicitly: with AutoConnection, a GUI-thread `panic()` would run `stop()` inside the exception hook. |
| after `active` | the `_panicked` property (below) |
| `start()` `:152-161`, after `if self.active: return` | log INFO "sending again after the emergency stop" if `_panicked` and a `stop()` has run since the last panic (`_stopped_id == _panic_id`), DEBUG otherwise; then `self._resumed_id = self._stopped_id`. Before `self._timer.start()`: `self._may_be_lit = True`. |
| `stop()` | first line, before `if not self.active: return`: `self._stopped_id = self._panic_id`. After `self._blackout()`: `self._may_be_lit = False`. |
| `_send()` `:213-217` | replace (below) |
| new methods after `close()` (`:179`), in the Lifecycle section | `panic()`, `_send_blackout_now()` and `_send_dark_frames()` (below) |

```python
        # Emergency stop bookkeeping. Each panic() takes a new id first thing; only dark frames go out while
        # _panic_id != _resumed_id (_panicked). panic() writes only _panic_id, the GUI thread only the other two, so a
        # panic() can't be lost to a start() running at the same time.
        self._panic_ids   = itertools.count(1)
        self._panic_id    = 0                # the latest panic() (any thread)
        self._stopped_id  = 0                # the latest panic() a stop() has run after (GUI thread)
        self._resumed_id  = 0                # the latest panic() start() has resumed from (GUI thread)
        self._may_be_lit  = False            # True from just before start()'s first frame until stop()'s blackout

    @property
    def _panicked(self) -> bool:
        """True from the moment panic() starts until a stop() has run after it
        and then start(): until then _send() lets only dark frames out."""
        return self._panic_id != self._resumed_id
```

Why ids rather than a bool that `start()` clears: a `panic()` on another thread can land while `start()` runs. With a
bool, `start()` could read "no panic", the panic could set the flag, and `start()` could then clear it, or clear a
panic whose own queued `stop()` hasn't run yet. Here `panic()` only takes a new id (`next()` on an
`itertools.count` is atomic under the GIL); `stop()` records the latest id it has run after, and `start()` resumes
only up to that id. No field has two writers, so no update can be lost, and a panic that came after the last `stop()`
stays in force through `start()` until its own `stop()` has run. Ids are unique, so even two panics storing their
ids out of order leave `_panic_id != _resumed_id` (dark) until a later `stop()` and `start()`.

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
        """(docstring as in the code)"""
        try:
            self._panic_id = next(self._panic_ids)         # first: from here on _send() lets only dark frames out
            if self._closed:
                log.debug('DMX: emergency stop: output closed, nothing to black out')
                return
            if not self._may_be_lit:                       # never started, or stop() already blacked out (M5)
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
        If the lock isn't free within _PANIC_LOCK_TIMEOUT_S, the frames go out
        without it, and then, once the send holding it has finished (it may
        have been a show frame, going out after them), BLACKOUT_REPEATS more.
        Logs only after the lock is released."""
        errors = []
        locked = self._send_lock.acquire(timeout=_PANIC_LOCK_TIMEOUT_S)
        try:
            self._send_dark_frames(errors)
        finally:
            if locked:
                self._send_lock.release()
        attempts = BLACKOUT_REPEATS
        if not locked:                                     # a frame in flight may follow those: black out after it
            if self._send_lock.acquire(timeout=_PANIC_RETRY_TIMEOUT_S):
                try:
                    self._send_dark_frames(errors)
                    attempts += BLACKOUT_REPEATS
                finally:
                    self._send_lock.release()
                log.warning('DMX: emergency blackout sent without the send lock (a send seemed stuck), '
                            'then again once that send had finished')
            else:
                log.warning('DMX: emergency blackout sent without the send lock; the stuck send never finished, '
                            'so the queued stop() blacks out after it')
        for e in errors:
            log.error(f'DMX: emergency blackout frame not sent: {e!r}')
        log.warning(f'DMX: emergency blackout sent ({attempts - len(errors)} of {attempts} frames)',
                    extra={'tone': Tone.OFF})

    def _send_dark_frames(self, errors: list[Exception]):
        """BLACKOUT_REPEATS dark frames straight through the sender; errors are
        collected, not raised or logged (the caller may hold the send lock)."""
        sender, port = self._sender, self.port             # one read each: configure() may swap them
        for _ in range(BLACKOUT_REPEATS):
            try:
                self._sequence = next_sequence(self._sequence)
                sender.send(build_artdmx(_BLACKOUT, port, self._sequence))
            except Exception as e:
                errors.append(e)
```

`panic()` decides whether to send from `_may_be_lit`, not from `state`. `state` only becomes `'sending'` in
`_update_status()`, after `_send()` has released the lock, so start()'s first frame is out while `state` still says
`'off'`; `_may_be_lit` is set before that frame. Both are plain Python attributes (M5).

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
| before `self.midi_out = MIDIOutput()` | `_space_lock` and `_space_armed` (snippet A, first part): opening the saved MIDI port re-arms SPACE, so they must exist first |
| after `:65` (`self.output = …`), before the engine | the registrations (snippet A, second part). They must come before `_apply_settings` (`:135`), which can start DMX from saved settings. |
| `_on_control_mode_changed` `:261-272`, before `self.output.select(mode)` | snippet B (re-arm). Before, not after: a stop on another thread between the two would otherwise find the arm still used up; this way it still sees DMX mode and leaves the arm alone. |
| new section before `# Qt event overrides` (`:352`) | `# Emergency stop` + `_midi_emergency_stop`, `_rearm_space`, `_open_midi_port` (snippet C) |
| every `self.midi_out.open(...)` (`_open_saved_midi_port`, `_reset_settings`, `_refresh_midi_ports`, `_on_midi_port_changed`) | `self._open_midi_port(...)` (Q12) |
| `closeEvent` `:371-382`, after `self.dmx_out.close()` (`:380`) | `self.safety.unregister('dmx')` and `self.safety.unregister('midi')`. They go last, so an exception earlier in `closeEvent` still reaches registered stops. `closeEvent` is safe to run twice (Ctrl+C during a close, test teardown): every call in it is idempotent. |

A:
```python
        # SoundSwitch's blackout note: due on the next emergency stop in MIDI mode (Q10, Q12). Before the MIDI port
        # opens, since opening one re-arms it
        self._space_lock  = threading.Lock()     # guards _space_armed; the stop may run on any thread
        self._space_armed = True
        ...
        # Emergency stop: on an unhandled exception, DMX goes dark first, then SoundSwitch gets all notes off and,
        # once per MIDI enable or port, its blackout note (design Q2, Q10, Q12)
        self.safety = safety if safety is not None else EmergencyStop()
        self.safety.register('dmx', self.dmx_out.panic)
        self.safety.register('midi', self._midi_emergency_stop)
```
B:
```python
        if mode == 'MIDI':
            self._rearm_space()                   # before select(): a stop in between still sees DMX, keeps the arm
        self.output.select(mode)
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
            self._rearm_space()

    def _rearm_space(self):
        """The next emergency stop in MIDI mode sends SPACE again: MIDI was
        (re)enabled (Q10) or a MIDI port was opened (Q12)."""
        with self._space_lock:
            self._space_armed = True

    def _open_midi_port(self, label: str | None) -> bool:
        """midi_out.open(label); a port that opens re-arms SPACE (Q12):
        SoundSwitch on it hasn't had SPACE through this connection."""
        if not self.midi_out.open(label):
            return False
        self._rearm_space()
        return True
```

Q12 counts every successful open: the user choosing a port, Reset, the saved port at startup, and the default port
reconnecting in `_refresh_midi_ports` (e.g. loopMIDI started after PyLZR). A failed open leaves the arm as it was.

The test-and-clear under `_space_lock` means two stops on two threads at once send SPACE once between them. The lock
is held only for the swap (no calls out), so it can't deadlock or delay anything. The mode is checked when the stop
runs, not by registering and unregistering on each mode switch. That gives one registration and no state to keep in
step with `_on_control_mode_changed`. `OutputSwitch.active` is a plain `str` attribute, so reading it from another
thread is safe.

Under Q1 the dropdown and `output.active` stay on DMX after the stop. Choosing MIDI re-arms SPACE, calls
`dmx_out.stop()` (already stopped, so it only records that a stop has run since the panic) and closes the tester;
choosing DMX again calls `dmx_out.start()`, which resumes the show.

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
| `DMXOutput._send_dark_frames` | `dmx/dmx_output.py` | `(errors: list[Exception]) -> None` |
| `DMXOutput._stop_requested` | `dmx/dmx_output.py` | `pyqtSignal()`, connected `QueuedConnection` to `stop` |
| `DMXOutput._send_lock` | `dmx/dmx_output.py` | `threading.Lock()` |
| `DMXOutput._panicked` | `dmx/dmx_output.py` | read-only property, `bool`: `_panic_id != _resumed_id` (True from `panic()` until a `start()` after a `stop()`) |
| `DMXOutput._panic_ids`, `_panic_id`, `_stopped_id`, `_resumed_id` | `dmx/dmx_output.py` | `itertools.count(1)`; `int`s, written by `panic()`, `stop()`, `start()` respectively |
| `DMXOutput._may_be_lit` | `dmx/dmx_output.py` | `bool`: set by `start()` before its first frame, cleared by `stop()` after its blackout |
| `_PANIC_LOCK_TIMEOUT_S`, `_PANIC_RETRY_TIMEOUT_S` | `dmx/dmx_output.py` | `0.005`, `0.1` |
| `MIDIOutput.panic` | `midi/midi_output.py` | `(note: int \| None = None) -> bool` (True if the note's ON was sent) |
| `MIDIOutput._send_lock` | `midi/midi_output.py` | `threading.Lock()` |
| `_NOTE_ON`, `_NOTE_OFF`, `_CONTROL_CHANGE`, `_ALL_NOTES_OFF`, `_VELOCITY`, `_PANIC_LOCK_TIMEOUT_S` | `midi/midi_output.py` | `0x90`, `0x80`, `0xB0`, `123`, `112`, `0.1` |
| `BLACKOUT_NOTE` | `midi/key_map.py`, exported by `pylzr.midi` | `106` (SPACE) |
| `MainWindow.__init__` | `gui/main_window.py` | `(safety: EmergencyStop \| None = None)`; attributes `safety`, `_space_lock`, `_space_armed` |
| `MainWindow._midi_emergency_stop`, `MainWindow._rearm_space` | `gui/main_window.py` | `() -> None` |
| `MainWindow._open_midi_port` | `gui/main_window.py` | `(label: str \| None) -> bool` (re-arms SPACE when the port opens, Q12) |
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
| `DMXOutput.panic` | caller's thread | Takes a new `_panic_id` (so `_panicked`), sends under `_send_lock`, emits `_stop_requested` |
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
  `_PANIC_LOCK_TIMEOUT_S` (5 ms). If that ever expires, it sends without the lock: the blackout isn't delayed, and
  later show frames are still blocked by the flag.
- *The 5 ms backstop and the frame in flight.* The lock can be held past 5 ms if the GUI thread is descheduled mid-send
  (an OS time slice, or waiting for the GIL: CPython's switch interval is also 5 ms). That thread has already passed
  the flag check, so its show frame goes out *after* `panic()`'s unlocked dark frames. So `panic()` then waits up to
  `_PANIC_RETRY_TIMEOUT_S` (0.1 s) for the lock, which means that send has finished, and sends the blackout again
  under it: the last frame out is dark. If even that wait expires, it logs a warning and the queued `stop()` blacks
  out once the GUI thread is free. Either way M2 weakens in this case to "the last frame is dark", not "no lit frame
  after the first dark one"; the window is one frame.
- The same lock removes the M6 races: sequence numbers stay unique, and `last_error`/`dropped` have one writer at a
  time.

Deadline: the stop runs before any logging (M3), and the three datagrams go back to back, so dark frames leave within
microseconds of the hook starting (plus at most one in-flight GUI frame). The 25 ms budget holds as long as the GUI
thread isn't stuck. If it is stuck, the hook isn't running there anyway.

---

## 6. Edge cases

| Case | Handling |
|---|---|
| DMX off (MIDI mode) | `panic()`: flag set, `_may_be_lit` False → DEBUG line, nothing sent; the queued `stop()` only records that a stop has run since the panic, so the next `start()` sends the show. |
| `panic()` between start()'s first frame and its status update | `_may_be_lit` is already True (set before that frame), so the blackout goes out; `state` would still say `'off'` there |
| DMX closed (after `closeEvent`) | `panic()`: `_closed` → nothing. Also, `closeEvent` has already unregistered both stops. |
| `panic()` after the Qt object is deleted (exit) | Python attributes still readable; frames sent; the `emit` raises `RuntimeError`, which `panic()` catches and logs at DEBUG |
| GUI tick while `panic()` holds the lock (FFT case) | waits µs, then sees the flag: nothing sent |
| GUI frame in flight when `panic()` starts | goes out before the first dark frame (the lock orders them) |
| `configure()` between `panic()` and the queued `stop()` | old node: `configure()`'s own blackout (dark: allowed); new node: its `_tick()` is blocked by the flag; the queued `stop()` blacks out the new node |
| `start()` racing with a `panic()` on another thread | no `stop()` has run since that panic, so `start()` doesn't end it (DEBUG line): its frames are blocked, and the panic's queued `stop()` then stops the new run (dark). The user switches Control Mode again to resume. A panic landing while `start()` runs can't be lost: `panic()` only writes `_panic_id`, `start()` only `_resumed_id`. (Before the review follow-up, `start()` cleared a bool flag, which let show frames out until the queued `stop()`.) |
| `panic()`, then a `stop()`, then `start()` in the same event-loop pass | the `stop()` ran after the panic (blackout, timer stopped), so `start()` resumes and the queued `stop()` then stops it again. A user can't do this (each mode change is a separate event, queued after the panic's `stop()`), so it's accepted. |
| User re-enables DMX (MIDI → DMX) | the MIDI choice's `stop()` (or the panic's own) has run since the panic, so `start()` resumes (INFO line) and sends the show at once |
| A send fails (`OSError`) | `UdpSender` returns False and sets `last_error`; the other copies still go out |
| A send raises (`RuntimeError`: sender closed by a concurrent `configure()`) | collected and logged after the lock is released; the queued `stop()` blacks out the new node |
| `panic()` can't get the lock within 5 ms (GUI thread descheduled mid-send) | sends anyway; then waits up to 0.1 s for that send to finish and sends the blackout again, so the frame in flight isn't the last one (§5); WARNING logged. If the second wait expires too, WARNING, and the queued `stop()` blacks out after it. |
| Queued `stop()` itself raises | hook → trigger → `panic()` (`_may_be_lit` still True) → dark frames → stop queued again. Keeps the laser dark, once per event-loop pass; logging is bounded by Q7. Accepted. |
| MIDI port not open | `MIDIOutput.panic()` returns False, DEBUG line; SPACE stays armed (Q11) |
| MIDI send raises (`RtMidiError`, driver error, port closed underneath) | caught per message, ERROR; remaining messages still tried; `panic()` returns whether SPACE's ON went out (if not, it stays armed) |
| MIDI send stuck in the driver on another thread | `acquire(timeout=0.1)` fails → ERROR, returns False. DMX already ran first. |
| `close()` / `open()` on the GUI thread during a MIDI panic on the FFT thread | `close_port()` waits for the lock; `panic()` used its own `out` reference |
| Second and later stops in MIDI mode | all-notes-off only (Q10), until Control Mode is switched to MIDI again or a MIDI port is opened (Q12) |
| Two stops at once on two threads, MIDI mode | `_space_lock` test-and-clear: SPACE once; all-notes-off twice |
| A stop on another thread while Control Mode switches to MIDI | SPACE is re-armed before `output.select('MIDI')`: a stop before the select sees DMX and leaves the arm alone; one after it finds it armed |
| MIDI port opened (user choice, Reset, startup, default port reconnecting) | SPACE re-armed (Q12); a failed open leaves the arm as it was |
| DMX mode | `'midi'` stop does nothing (`output.active != 'MIDI'`) and doesn't use up the SPACE arm |
| Stop callable raises inside `trigger()` | `log.exception`, the rest still run, `triggered` stays True |
| `trigger()` from inside a stop (same thread) | returns at once |
| Same error on every frame (FFT bug: ~43/s) | stop runs every time (DMX: DEBUG once off; MIDI: all-notes-off each time, SPACE once); log: full traceback once, then one line at 2, 4, 8, … (Q7) |
| Log panel's own slot raises on every record | the loop dies out: the 3rd identical error isn't logged, so no new record reaches the panel |
| Exception before any stop is registered (in `QApplication()`, `style.apply`) | trigger logs DEBUG "nothing registered"; traceback logged to the console (M4) |
| Exception escaping `MainWindow.__init__` after saved settings started DMX | stops registered at `:65+`, before `_apply_settings`; top-level hook → blackout; then `atexit` → `panic()` again (`_may_be_lit` still True; Qt objects possibly gone, M5) |
| Exception inside `closeEvent` after `dmx_out.stop()` | stops still registered (unregistered last); DMX already off. The rest of `closeEvent` is skipped, as today; out of scope. |
| Ctrl+C in a slot | stop, one WARNING line (no traceback, no hint), `closeAllWindows` queued → `closeEvent` → app quits (Q8) |
| Ctrl+C twice | the second queued `closeAllWindows` finds no visible window: no-op |
| Ctrl+C during `closeEvent` | the stop runs; the queued close skips a window that's already closing; whatever `closeEvent` hadn't done yet is skipped, as for any exception there (out of scope) |
| Ctrl+C during startup (before `exec_()`) | raised in `main()` → top-level hook → stop + WARNING; the process exits (the queued close never runs) |
| Ctrl+C while the hook is already running (another error's stop or logging) | swallowed: `panic()`, `trigger()` and the hook all catch `BaseException`. Inside `panic()` it ends the blackout loop early (the `finally` releases the lock), logs "emergency stop failed" and skips queueing `stop()`; the flag stays set, so no show frame goes out. Elsewhere in the hook, `_last_resort` prints it. The app doesn't quit; pressing Ctrl+C again does. Accepted (review finding 6). |
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
   Then, from the first dark frame on, every frame is dark, and at least one tick ran after panic()'s first send
   started (a counter: the test fails if the race was never exercised). Without the flag check this fails every run.
   It doesn't catch a missing send lock (test 10 does).
4. `test_panic_while_stopped_sends_nothing(out, qapp, caplog)`: `universe.set(1, 255)`, `panic()`,
   `processEvents()` → `sent == []`, not active; DEBUG "nothing to black out"; `start()` afterwards sends `SHOW` (the
   panic's `stop()` has run). Lit, so the last check can't pass on a dark show frame.
5. `test_panic_after_close_sends_nothing(out)`: `start()`, `close()`, `n = len(sent)`, `panic()` → `len(sent) == n`.
6. `test_each_panic_copy_has_its_own_sequence_number(out)`: `start()`, `panic()` → sequences `[1, 2, 3, 4]`.
7. `test_panic_never_raises(out, monkeypatch, caplog)`: `start()`; `monkeypatch.setattr(out._sender, 'send', raiser)`
   with `raiser` raising `RuntimeError` → `panic()` returns; 3 ERROR records "frame not sent".
8. `test_panic_from_another_thread(out)`: `start()`; run `out.panic` in a `threading.Thread`, join → 3 dark frames
   after the first; `wait_until(lambda: not out.active)` (the queued stop reached the GUI thread).
9. `test_panic_after_the_qt_object_is_gone_still_blacks_out()`: a local `DMXOutput(socket_factory=FakeSocket)` (not
   the fixture), `start()`, `sip.delete(o)`, `o.panic()` → no exception, `frames()[-3:] == DARK`.

Added in the review follow-up (§10). Tests 10 and 11 patch `dmx_output.build_artdmx`, which `_send()` calls while
holding the send lock, and wait with `spin_until` (sleeps; never processes Qt events, which could run the queued
`stop()` while this thread holds the lock):

10. `test_a_frame_being_sent_when_panic_starts_goes_out_before_the_blackout(out, monkeypatch)`: the send lock,
    deterministically. `_PANIC_LOCK_TIMEOUT_S` raised to 5 s. `start()`; in the patched `build_artdmx` (main thread,
    first call) start `out.panic` in a thread, wait until `out._panicked`, then `join(0.1)`; `out._tick()` →
    `frames() == [SHOW, SHOW] + DARK`. Without the lock in `_send()`, panic's dark frames go out during the join and
    the tick's frame after them.
11. `test_a_frame_still_in_flight_when_panic_stops_waiting_is_followed_by_dark(out, monkeypatch, caplog)`: the GUI
    side holds the lock past 5 ms. `_PANIC_RETRY_TIMEOUT_S` raised to 5 s. The patched `build_artdmx` starts the panic
    thread and waits until its 3 dark frames are out (sent without the lock) → `frames() == [SHOW] + DARK + [SHOW] +
    DARK`; WARNING "then again once that send had finished".
12. `test_a_start_before_the_panics_own_stop_sends_nothing_lit(out, qapp)`: `universe.set(1, 255)`, `panic()`,
    `start()` → `frames() == []`; `processEvents()` → not active, all frames dark; `start()` → `SHOW`.
13. `test_panic_right_after_the_first_frame_blacks_out(out, monkeypatch)`: `out._update_status` patched to call
    `panic()` on its first call (recording `out.state`); `start()` → recorded state `'off'`,
    `frames() == [SHOW] + DARK`.

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
    `all(f == bytes(512) for f in frames()[i:])`. A counter on `w.dmx_out._send` (the GUI thread's ticks) asserts at
    least one lit tick ran between panic()'s first send starting and its third finishing, so the test fails if the
    race was never exercised.
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
28. `test_two_stops_at_once_send_space_once(make_window)`, deterministic (review follow-up): the window's class is
    swapped for a subclass whose `_space_armed` property, read on the main thread the first time, starts a second
    `w.safety.trigger` on another thread and joins it for 0.1 s before returning. `w.safety.trigger('first')`; join
    the second → exactly one `SPACE_ON` and two `ALL_OFF`. With `_space_lock` the second stop waits for the first's
    test-and-clear; without it both read the arm as set and send SPACE twice. (The first version, two threads behind a
    `threading.Barrier(2)`, passed with the lock removed.)
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

Added in the review follow-up (§10):

36. `test_a_stop_during_the_switch_to_midi_sends_space(make_window, monkeypatch)`: trigger (SPACE used up);
    `set_mode('DMX')`; `w.output.select` patched to call the real one, then `w.safety.trigger(...)`;
    `set_mode('MIDI')` → `note_ons() == [[106, 112], [106, 112]]`.
37. `test_opening_a_midi_port_rearms_space(make_window)` (Q12): `'PyLZR-MIDI 1'` added; trigger (SPACE to the virtual
    port); `settings_panel.midi_port_changed.emit('PyLZR-MIDI 1')`; trigger twice → `note_ons()` has SPACE twice
    (once per port).

Expected count after the task: 1318 + 1 (7.2) + 9 (7.3: 8, the first run on two OSes) + 9 (7.4) + 36 (7.5: 35, the
atexit test run twice) = **1373**. After the review follow-up: + 4 (7.4 #10–13) + 2 (7.5 #36–37) = **1379**.

---

## 8. Verification

```powershell
.venv\Scripts\python -m pytest tests/test_key_map.py tests/test_midi_output.py tests/test_dmx_output.py -q
.venv\Scripts\python -m pytest tests/test_safety.py -q
.venv\Scripts\python -m pytest tests/test_main_window_dmx.py tests/test_main_window.py tests/test_engine.py -q
.venv\Scripts\python -m pytest -q                     # 1379 passed, nothing skipped
.venv\Scripts\ruff check .
git diff --exit-code -- tests/golden/                 # golden files unchanged
```

The race and ordering tests (7.4 #3, #10, #11; 7.5 #23, #28) must pass every time. Before handing over, run them 20
times in a row:
`for ($i=0; $i -lt 20; $i++) { .venv\Scripts\python -m pytest tests/test_safety.py tests/test_dmx_output.py -q -k "dark or show_frame or in_flight or being_sent or two_stops" }`.
To confirm they'd catch a regression, remove each fix in turn and see its test fail, then restore it: the flag check
in `_send()` (#3, #23), the send lock in `_send()` (#10), the second blackout in `_send_blackout_now()` (#11),
`_space_lock` in `_midi_emergency_stop` (#28), and for the follow-up fixes #12, #13, #36 and #37 (§10).

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

---

## 10. Review follow-up (after `efa64b9`)

A review of `efa64b9` against this plan found the gaps below. All but finding 6 are fixed in a follow-up commit;
the sections above describe the code after it.

| # | Finding | Change |
|---|---|---|
| 1 | If the GUI thread held the send lock past 5 ms (descheduled mid-send), `panic()` sent without it and the in-flight show frame went out after the dark frames | `_send_blackout_now()` then waits up to `_PANIC_RETRY_TIMEOUT_S` (0.1 s) for that send to finish and blacks out again, so the last frame is dark (§3.3, §5). Test 7.4 #11. |
| 2 | The race tests didn't catch a missing send lock or a missing `_space_lock` (they passed 10/10 with either removed) | Deterministic tests: 7.4 #10 (send lock) and 7.5 #28 rewritten (`_space_lock`). Both now fail 5/5 with their lock removed. |
| 3 | `start()` cleared the flag, so a `start()` racing with a `panic()` on another thread let show frames out until the queued `stop()`; §6 claimed the flag blocked them | Panic ids instead of a bool (§3.3): `start()` resumes only from panics a `stop()` has run after, and no field has two writers, so a concurrent panic can't be lost. §6 rows corrected. Test 7.4 #12. |
| 4 | `panic()` decided from `state == 'off'`, which is still `'off'` when start()'s first frame goes out | `_may_be_lit`, set before that frame, cleared after stop()'s blackout (§3.3). Test 7.4 #13. |
| 5 | SPACE was re-armed after `output.select('MIDI')`, so a stop in between found it used up | Re-armed before the select (§3.6). Test 7.5 #36. |
| 6 | A Ctrl+C landing while the hook is running is swallowed | Accepted, no code change; documented in §6 and the design's failure modes. |
| 7 | The comment in `test_dmx_output.py` claimed `monkeypatch` is undone before `out.close()`; the race tests could pass without the race happening; opening another MIDI port didn't re-arm SPACE | Comment corrected; tick counters in 7.4 #3 and 7.5 #23; SPACE re-armed whenever a MIDI port opens (Q12, `_open_midi_port`), test 7.5 #37. `test_panic_while_stopped_sends_nothing` (7.4 #4) now uses a lit show frame, so its last check means something. |

Verification: full suite 3 runs (1379 passed each), the race and ordering tests 20 runs, `ruff check .` clean. Each
fix was removed in turn and its test failed 5 runs out of 5; every file was restored byte for byte.
