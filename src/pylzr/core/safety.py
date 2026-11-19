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


class _ExceptionHandler:
    def __init__(self, stop: EmergencyStop, on_handled: Callable[[], None] | None,
                 on_interrupt: Callable[[], None] | None):
        self._stop = stop
        self._on_handled = on_handled
        self._on_interrupt = on_interrupt
        self._seen: dict[tuple, int] = {}      # (type, file, line) of the innermost frame -> times seen; holds no frames
        self._handled_once = False
        self._lock = threading.Lock()

    def handle(self, exc_type, exc_value, exc_tb, thread_name: str | None = None) -> None:
        try:
            if issubclass(exc_type, KeyboardInterrupt):
                self._stop.trigger('interrupted')
                log.warning('Interrupted (Ctrl+C): outputs blacked out; quitting')
                if self._on_interrupt is not None:
                    self._on_interrupt()
                return
            self._stop.trigger('unhandled exception')                    # 1. stop first (M3)
            self._log(exc_type, exc_value, exc_tb, thread_name or threading.current_thread().name)   # 2.
            with self._lock:                                             # 3. what next: first error only
                first = not self._handled_once
                self._handled_once = True
            if first and self._on_handled is not None:
                self._on_handled()
        except BaseException:
            _last_resort(exc_type, exc_value, exc_tb)

    def handle_thread(self, args) -> None:
        if args.exc_type is SystemExit:
            return                                                       # as threading's own hook does
        self.handle(args.exc_type, args.exc_value, args.exc_traceback,
                    args.thread.name if args.thread is not None else None)

    def _log(self, exc_type, exc_value, exc_tb, thread_name: str) -> None:
        key = _innermost(exc_type, exc_tb)
        with self._lock:
            count = self._seen[key] = self._seen.get(key, 0) + 1
        if count == 1:
            log.error(f'Unhandled exception (thread {thread_name})', exc_info=(exc_type, exc_value, exc_tb))
        elif count & (count - 1) == 0:                                   # 2, 4, 8, … (Q7)
            log.error(f'The same error again ({count} times so far): {exc_type.__name__}: {exc_value}')


def _innermost(exc_type, tb) -> tuple:
    """(type, file, line) of the last traceback frame: what makes two errors 'the same'."""
    if tb is None:
        return exc_type, None, None
    while tb.tb_next is not None:
        tb = tb.tb_next
    return exc_type, tb.tb_frame.f_code.co_filename, tb.tb_lineno


def _last_resort(*exc_info) -> None:
    """The hook itself failed: print the original and the hook's own traceback
    to stderr, if there is one (pythonw has none)."""
    try:
        if sys.stderr is not None:
            traceback.print_exception(*exc_info, file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
    except BaseException:
        pass
