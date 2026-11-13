# Task 4: debounced settings writes (P5): implementation plan

Branch `hayden/components-pt3`, after `c5a2601 Emergency stop: review follow-up to efa64b9`. Task text: `PLAN.md`,
Task 4. Design: `docs/design/safety-phase.md` (Interfaces, Threading, Failure modes, Open questions).
Baseline: `pytest -q` gives **1379 passed**.

Decisions in force (all recorded in the design's Open questions):
- **Q3.** `FLUSH_MS = 400`, kept. The wait restarts on every change, so a killed app loses the changes made since
  input last paused for 400 ms (during a continuous drag, the drag so far).
- **Q12** (Task 3). Every successful MIDI port open re-arms SPACE, reconnects included. Unaffected by this task.
- **Q13.** No extra flush on exit paths that skip `closeEvent` (no `atexit`, no `aboutToQuit`). Pending changes
  there are written by Qt's `QSettings` destructor when the store is freed (§9).
- **Q14.** Qt's own automatic sync is held back by a `QSettings` subclass that ignores its `UpdateRequest` event, not
  by keeping pending values in a Python dict (§9). The PyQt6 spike re-checks it (`ROADMAP.md`).

Review changes (approved plan): the tests patch `FLUSH_MS` to a few ms, and only the two Q14 pinning tests use the
real 400 ms, without waiting it out (§7); the doc fixes in §1 are applied.

---

## 1. What the plan in PLAN.md misses (verified in this planning step)

Probed with PyQt 5.15.11 / Qt 5.15.2, offscreen, in a scratch script (since deleted):

| Behaviour | Result | Consequence |
|---|---|---|
| `setValue()`, then one `processEvents()`, plain `QSettings` | **written to disk** | Qt posts itself an `UpdateRequest` on the first change after a sync and syncs when the event loop delivers it (Qt docs: sync() "is called automatically … by the event loop at regular intervals"). Deferring only *our* `sync()` call, as PLAN.md describes, still writes on every event-loop pass, so a slider drag still writes on every step. |
| Same, with a subclass whose `event()` ignores `QEvent.UpdateRequest` | not written, after several passes | The subclass holds writes back until `sync()`. Fix: §3.1. |
| Constructing a second `QSettings` for the same file | **writes the first one's pending changes** | Qt syncs in the constructor. Matters for tests (§7): create no store before checking "not on disk yet". |
| A second `QSettings` reading a key that's pending in the first | sees the pending value | Instances in one process share Qt's cache. Tests that read a fresh `SettingsStore()` after the window changed something keep passing, and so do in-process restart tests, **with or without a flush**. They don't prove anything reached disk (§7.1). |
| Store deleted with a change pending | written | `~QSettings` writes pending changes (documented). The exit paths rely on it (§6, Q13). |
| No `QCoreApplication`: `setValue()` | not written until `sync()` or the destructor | Without an app, `set()` must sync at once, as PLAN.md says. |
| `sync()` when the folder can't be created (a file where the config folder should be) | doesn't raise; `status()` = `AccessError` (1); `value()` still returns the new value | A failed write is silent today (it doesn't abort, despite what the design says). |
| Next `sync()` after the folder is fixed, with nothing new set | **writes the kept value** | "Retried on next flush" holds: Qt keeps unwritten changes. |
| `status()` after that successful write | still `AccessError` | `status()` keeps the *first* error, so it can't detect recovery. Log once per store (§3.1). |
| `QTimer()` created with no `QCoreApplication` | fine | The store can always create its timer. |

### Doc mismatches and the fixes (1–7 applied to `PLAN.md` and the design at plan approval; 8 is in the code, §3)

1. **PLAN.md Task 4, Files:** `main_window.py:371-378` is stale. `closeEvent` is now `main_window.py:423-436`.
   `settings_store.py:83-87` and `tests/test_settings_store.py:77-81` are still right.
2. **PLAN.md Task 4, Change:** add "Qt's own sync on the next event-loop pass is held back (a `QSettings` subclass
   ignoring `UpdateRequest`)". Without it the change achieves nothing (table above).
3. **PLAN.md Task 4, Acceptance:** "a variant that closes within 50 ms of the last change still restores it" can't
   fail as written (shared cache, destructor). Replace with "a window closed right after a change has it **in the
   file on disk** when `closeEvent` returns, read before any other store is created". Add: "the flush comes after
   the blackout and before `engine.shutdown()`"; "Qt's automatic sync doesn't write between flushes".
4. **Design, Failure modes, `sync()` fails:** the "Today" column says "exception in a slot → abort". In fact
   `QSettings.sync()` never raises; today the failure is silent. The "After" column becomes "logged once (WARNING,
   per store); the value stays in memory (`get()` returns it) and is written by the next successful sync (next change
   or close)".
5. **Design, Threading, Settings bullet:** "at most one such stall per `FLUSH_MS` of user input" becomes "one write
   per pause of `FLUSH_MS` in changes (a continuous drag writes once, after it ends), plus one on close".
6. **Design, Interfaces:** add `pending` (property) and note the subclass (§4).
7. **Design, Migration step 4:** "`main_window.py` flushes in `closeEvent` before step 1's `dmx_out.close()`" becomes
   "right after `dmx_out.stop()` and `_close_dmx_tester()`, before `engine.shutdown()`".
8. **`SettingsStore` docstring** (`settings_store.py:47-53`): "set() saves immediately, so nothing is lost if the app
   is killed" is no longer true (§3.1 gives the new text). **`MainWindow` docstring** (`main_window.py:46-48`): "saved
   whenever they change" becomes "saved shortly after they change (debounced) and on close".

Q3's wording, as decided: the timer restarts on every change, so a killed app loses the changes made since input
last paused for 400 ms. During a continuous drag that is the whole drag so far, not just 400 ms.

---

## 2. What the user sees afterwards

| Situation | Today | After Task 4 |
|---|---|---|
| Drag a slider for 5 s | one `sync()` (file write) per slider step on the GUI thread (2–4 ms each) | no write during the drag; one write 400 ms after it ends |
| Change one setting and wait | written at once | written 400 ms later |
| Close the window right after a change | written at once | written by `closeEvent`, right after the blackout |
| Ctrl+C right after a change | written at once | the queued close runs `closeEvent`, which writes it |
| Unhandled exception, then a change | written at once | written 400 ms later (the app keeps running, Q1) |
| Reset to defaults | file cleared at once | same; any pending write is dropped first |
| Disk write fails (unwritable folder) | silent | one WARNING naming the file; the value is kept and written once writing works again |
| App killed (Task Manager, power loss) | nothing lost | changes since input last paused for 400 ms are lost (Q3) |

---

## 3. Changes by file

### 3.1 `src/pylzr/gui/settings_store.py`

| Lines | Change |
|---|---|
| `:1-3` imports | `from PyQt5.QtCore import QCoreApplication, QEvent, QSettings, QTimer`; add `from ..core.app_logger import get_logger` after the `..core` import block (`:5-8`) |
| after the imports | `log = get_logger('settings')`, `FLUSH_MS`, `_DeferredSettings`, `_app_exists()` (below) |
| `:47-53` class docstring | replace the second paragraph (below) |
| `:55-56` `__init__` | below |
| new, after `fixtures_folder` (`:62-66`) | `pending` property |
| `:83-87` `set()` | below |
| new, after `set()` | `flush()` |
| `:89-91` `clear()` | below |
| new, last | `_sync()` |

```python
log = get_logger('settings')        # 'pylzr.settings'

# Changes reach the file this long after the last one (design Q3). Dragging a
# slider changes a setting on every step, and each write takes a few ms on the
# GUI thread, so a drag is written once, after it ends.
FLUSH_MS = 400


class _DeferredSettings(QSettings):
    """QSettings that writes only when sync() is called (or when it's deleted).
    Plain QSettings also writes on the next event-loop pass after any change
    (it posts itself an UpdateRequest), which would defeat FLUSH_MS."""

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.UpdateRequest:
            return True                                   # ignored: SettingsStore decides when to write
        return super().event(event)


def _app_exists() -> bool:
    """Whether a QCoreApplication exists, so the flush timer can run. A
    function so tests can make the store act as if there were none."""
    return QCoreApplication.instance() is not None
```

Docstring, second paragraph:
```
    get() returns the saved value, or the default if missing, unreadable or
    invalid. set() stores the value at once (get() returns it) and writes the
    file FLUSH_MS after the last change, so dragging a slider writes once, not
    on every step; flush() writes now (the window calls it on close). Without
    a QCoreApplication there's no timer, and set() writes at once. Use it from
    the GUI thread only.
```

```python
    def __init__(self):
        self._qs = _DeferredSettings(QSettings.IniFormat, QSettings.UserScope, 'PyLZR', 'PyLZR')
        self._flush_timer = QTimer()                  # GUI thread; no parent: owned by this store
        self._flush_timer.setSingleShot(True)
        self._flush_timer.setInterval(FLUSH_MS)       # read here, so tests can patch FLUSH_MS before creating a store
        self._flush_timer.timeout.connect(self.flush)
        self._write_failure_logged = False            # QSettings.status() keeps its first error: log it once

    @property
    def pending(self) -> bool:
        """A change is waiting for the flush timer."""
        return self._flush_timer.isActive()

    def set(self, key: str, value):
        if key not in DEFAULTS:
            raise KeyError(key)
        self._qs.setValue(key, value)
        if _app_exists():
            self._flush_timer.start()                 # (re)start: written FLUSH_MS after the last change
        else:
            self._sync()

    def flush(self):
        """Write pending changes now. Cheap when nothing is pending."""
        self._flush_timer.stop()
        self._sync()

    def clear(self):
        """Remove every saved setting, in the file too, at once."""
        self._flush_timer.stop()
        self._qs.clear()
        self._sync()

    def _sync(self):
        self._qs.sync()
        if self._qs.status() != QSettings.NoError and not self._write_failure_logged:
            self._write_failure_logged = True
            log.warning(f'Settings: could not write {self.path}; changes are kept and written at the next '
                        'change or when PyLZR closes')
```

`get()`, `path`, `fixtures_folder`, `DEFAULTS` and `_VALID` don't change.

### 3.2 `src/pylzr/gui/main_window.py`

| Lines | Change |
|---|---|
| `:46-48` class docstring | "User settings are restored from the SettingsStore at startup and saved whenever they change." becomes "User settings are restored from the SettingsStore at startup, saved shortly after they change (the store waits for changes to pause) and written on close." |
| `closeEvent` `:423-436`, after `self._close_dmx_tester()` (`:428`) | `self.store.flush()                      # settings to disk before anything that can block (audio close, FFT wait)` |
| comment `:424-426` | becomes: "The blackout goes out first, then the settings are written, both before anything that could block (closing audio, waiting for the FFT thread); the socket is released last. See docs/design/safety-phase.md." |

Resulting order in `closeEvent`: `dmx_out.stop()`, `_close_dmx_tester()`, `store.flush()`, `engine.shutdown()`,
`discovery.close()`, `midi_out.close()`, `dmx_out.close()`, `safety.unregister('dmx')`, `safety.unregister('midi')`,
log handler removed, `super().closeEvent(event)`.

Why there: after the blackout, because a write is file I/O and can stall (a slow disk, antivirus), and P2 puts the
blackout before anything that can block. Before `engine.shutdown()`, because that one is the known blocker (PortAudio
close, `fft_thread.wait(2000)`), and a user who kills a hung close should still keep their settings. That is "before
`dmx_out.close()`", as PLAN.md asks, just earlier than its stale line reference suggests. Nothing after the flush in
`closeEvent` calls `store.set()` (read: `engine.shutdown`, `discovery.close`, `midi_out.close`, `dmx_out.close` don't
emit any signal that reaches `_save_changes` or the device/port/node handlers). If something ever did, the change would
still be written, by `~QSettings` when the window is deleted.

`_reset_settings` (`:192-201`) doesn't change. `_apply_settings(DEFAULTS)` emits changes, so `set()` starts the
timer; `store.clear()` then stops it and clears the file at once.

### 3.3 Docs
Already done at plan approval: `PLAN.md` Task 4 and `docs/design/safety-phase.md` (§1 fixes 1–7; Q3, Q13 and Q14
decided), and the Q14 re-check in `ROADMAP.md`'s PyQt6 spike. At the end (checklist step 7): Task 4 marked done,
`HANDOFF.md`.

---

## 4. New and changed names

| Name | Where | Signature / value |
|---|---|---|
| `FLUSH_MS` | `gui/settings_store.py` | `400` (ms), read when a store is created |
| `log` | `gui/settings_store.py` | logger `'pylzr.settings'` |
| `_DeferredSettings` | `gui/settings_store.py` (private) | `QSettings` subclass; `event(event) -> bool` ignores `QEvent.UpdateRequest` |
| `_app_exists` | `gui/settings_store.py` (private) | `() -> bool` |
| `SettingsStore.pending` | `gui/settings_store.py` | property, `bool` (flush timer active) |
| `SettingsStore.flush` | `gui/settings_store.py` | `() -> None` |
| `SettingsStore.set` | `gui/settings_store.py` | unchanged signature; writes after `FLUSH_MS`, or at once with no app |
| `SettingsStore.clear` | `gui/settings_store.py` | unchanged signature; stops the timer, then clears and writes at once |
| `SettingsStore._flush_timer`, `_write_failure_logged`, `_sync()` | `gui/settings_store.py` (private) | `QTimer` (single shot, `FLUSH_MS`); `bool`; `() -> None` |

---

## 5. Threading and timers

| Piece | Runs on | Notes |
|---|---|---|
| `SettingsStore()` | GUI thread (`MainWindow.__init__`, `:61`) | creates the `QTimer`, so the timer lives on the GUI thread |
| `set()` | GUI thread only. Callers: the `_save_changes` lambdas (`:183-189`), `_on_audio_device_changed` (`:249`), `_on_midi_port_changed` (`:273`), `_on_dmx_node_changed` (`:300-301`) | all are slots of GUI widgets or GUI-thread handlers. The FFT thread, the exception hook and the emergency stops never touch the store. |
| flush timer `timeout` → `flush()` | GUI thread, from the event loop, `FLUSH_MS` after the last `set()` | single shot; `start()` on an active timer restarts it |
| `flush()` from `closeEvent`, `clear()` from `_reset_settings` | GUI thread | stop the timer first, so it can't fire afterwards |
| Qt's `UpdateRequest` | posted by `setValue()` to the GUI thread | ignored by `_DeferredSettings.event()` |
| `~QSettings` | whichever thread frees the store (the GUI thread: the window is freed there, or at interpreter exit on the main thread) | writes anything still pending |

**Without a `QCoreApplication`** (a script, or a test that never created one), `_app_exists()` is False and `set()`
writes at once, as today. **With an app but no running event loop** (a test that doesn't process events, or after
`exec_()` returns), the timer never fires. Changes then reach disk through `flush()`, `clear()`, another store being
created, or the store being deleted (§1).

Cost: one `sync()` measured 0.2 ms (small file, already there) to 2.5 ms (first write) here. The design's 2–4 ms
stays as the planning figure. `pending` and `start()` cost microseconds.

The test suite's app is session-scoped (`conftest.py:39-41`), so whether one exists depends on test order. Tests that
care either request `qapp` (timer path) or monkeypatch `settings_store._app_exists` (no-app path). §7.

---

## 6. Edge cases

| Case | Handling |
|---|---|
| Many changes in a row (slider drag) | each `set()` updates the value and restarts the timer; one write `FLUSH_MS` after the last |
| `get()` right after `set()` | returns the new value (Qt's cache) |
| Another `SettingsStore` created while changes are pending (tests do this) | its construction writes them (Qt syncs on construction); it reads the new values |
| Normal close | `closeEvent` flushes after the blackout, before `engine.shutdown()`; the timer is stopped |
| `closeEvent` hangs in `engine.shutdown()` and the user kills the app | settings are already on disk |
| Ctrl+C (Q8) | the hook runs the stop, then `_quit_as_if_closed` queues `closeAllWindows` → `closeEvent` → flush. The timer can't fire first: the close is queued with a 0 ms timer, ahead of a 400 ms one. |
| Ctrl+C during `closeEvent`, before the flush | the rest of `closeEvent` is skipped (accepted, Task 3 §6). Pending changes are written by `~QSettings` when the window and its store are freed (window deleted, or at interpreter exit). |
| Unhandled exception, app keeps running (Q1) | the store is untouched; the timer keeps working; pending changes are written as usual |
| Exception inside the flush itself | can't come from `sync()` (it never raises) or `status()`. A failing log handler would go to the hook like any slot error, and the value stays pending in Qt's cache, written by the next `sync()` or `~QSettings`. |
| Exception escaping `MainWindow.__init__` (startup) | nothing is pending: `_save_changes()` connects the savers at the very end of `__init__`, after the restore, and the startup MIDI open doesn't save |
| `atexit` path: process exits without `closeEvent` | No code path quits that way today: nothing calls `QApplication.quit()`, and Ctrl+C closes windows. If one appears, `~QSettings` writes the pending changes when the window is freed at `sys.exit` (the `main()` frame is released before `atexit` runs). Q13 (decided): no extra exit flush. An `atexit` flush registered in `main()` would run *before* the safety stop's `atexit` blackout (last in, first out), putting file I/O ahead of the blackout. |
| Emergency-stop `atexit` trigger | unchanged; it never touches settings |
| Killed process (power loss, Task Manager, `os._exit`) | changes since input last paused for 400 ms are lost (Q3, accepted) |
| Reset to defaults | `_apply_settings(DEFAULTS)` starts the timer; `clear()` stops it, clears the file and writes at once; nothing is pending afterwards |
| Write fails (folder not creatable, read-only, disk full) | `sync()` doesn't raise; one WARNING per store naming the file; `get()` keeps returning the new value; the next successful `sync()` (next change, or close) writes it. Recovery isn't logged, since `status()` keeps its first error. |
| A hand-edited file changed on disk while the app runs | as today: Qt re-reads on sync and merges; pending keys win |
| Two windows in one process (tests) | each has its own store; they share Qt's cache; each flushes on its own close |
| A store freed with its timer running (tests' temporary stores) | the timer is freed with it; `~QSettings` writes the change |
| `set()` from a non-GUI thread | not supported (docstring). Qt would warn "Timers cannot be started from another thread" and the write would wait for the next flush. No caller does it. |
| Settings changed while a modal dialog runs its own event loop | the timer fires in that loop as usual |

---

## 7. Tests

Timing: tests that need the timer to fire patch `FLUSH_MS` to a few ms (`settings_store.FLUSH_MS` is read when a store
is created, so the patch goes in before `SettingsStore()` or `make_window()`). Only the two Q14 pinning tests (#1,
#2) use the real 400 ms, and neither waits it out: each checks that nothing is written while the timer is still
running, then ends with `flush()`. Tests that check "not written yet" never process events with a patched few-ms
value, since the timer could fire during the check.

Helpers in `tests/test_settings_store.py`:
- `on_disk(store) -> str`: `Path(store.path).read_text()` if the file exists, else `''`. It reads the file directly.
  A `SettingsStore()` or `QSettings()` would write pending changes first (§1), so tests that check "not written yet"
  must not create one before checking.
- fixture `fast_flush(monkeypatch)`: `monkeypatch.setattr(settings_store, 'FLUSH_MS', FAST_MS)` with `FAST_MS = 5`;
  returns `FAST_MS`.

### 7.1 Existing tests

- `tests/test_settings_store.py:77-81` `test_each_change_is_written_to_disk_immediately`: **replaced** by 7.2 #3, #4
  and #6. "Immediately" is now true only without an app.
- Unchanged, and why they still pass:
  - Tests that build a fresh `SettingsStore()` after a change: `test_round_trip_survives_a_new_instance`,
    `test_clear`, `test_reset_to_defaults`, `test_failed_device_switch_is_not_saved`, and
    `test_main_window_dmx.py:99-101, 133-134, 271-272`. The fresh store's construction writes anything pending and
    reads through the shared cache. They check what the app reads back, not the disk; the disk is covered by 7.2.
  - Tests that seed values with `SettingsStore().set(...)` before `make_window()`: `test_hand_edited_cutoffs_…`,
    `test_saved_audio_device_…`, `test_missing_saved_devices_…`, `test_saved_loopmidi_…`,
    `test_main_window_dmx.py:119-120`. The temporary store is freed at once (its destructor writes the value), and
    the window's store would see it in the cache anyway.
  - `test_settings_restored_after_restart`: `first.close()` flushes. It would pass even without the flush (shared
    cache), which is why 7.2 #10 exists.
  - `test_unreadable_values_…`, `test_unusable_dmx_values_…`: write with a plain `QSettings` and `sync()`
    themselves.
- Window tests that end with the `make_window` teardown now flush in `closeEvent`. That's one more cheap `sync()` per
  window and no assertion change. None of them waits for the timer.

### 7.2 New tests: `tests/test_settings_store.py`

Imports: `gc`, `time`; `from PyQt5.QtCore import QSettings, Qt` (already there);
`from helpers import dmx_packets, wait_until`; `from pylzr.gui import settings_store`;
`from pylzr.gui.settings_store import DEFAULTS, SettingsStore` (already there).

**The store** (each requests `qapp` unless it says otherwise, so the timer path is used regardless of test order)

1. `test_a_change_waits_for_the_flush_timer(qapp)`, Q14 pin, real value: `settings_store.FLUSH_MS == 400` and
   `store._flush_timer.interval() == 400`. `store.set('audio/gain', 2.5)` → `store.pending`,
   `'gain=2.5' not in on_disk(store)`. Then `qapp.processEvents()` three times → still not on disk and still pending
   (Qt's own write is held back; plain `QSettings` writes on the first of these passes). Then `store.flush()` → on
   disk. No waiting: the passes take microseconds against 400 ms.
2. `test_many_changes_are_written_once_on_flush(qapp)`, Q14 pin, real value: wrap `store._qs.sync` (instance
   attribute) with a counter that calls the real one. 100 × (`store.set('audio/gain', 1 + i / 100)`,
   `qapp.processEvents()`), like a drag with events running between steps (a few ms in all against 400 ms) → counter
   0, `'gain=' not in on_disk(store)`, `store.pending`. `store.flush()` → counter 1, `'gain=1.99' in on_disk(store)`,
   `not store.pending`.
3. `test_the_timer_writes_the_change(qapp, fast_flush)`: `set('audio/gain', 2.5)` →
   `wait_until(lambda: 'gain=2.5' in on_disk(store), timeout=1.0)`; `not store.pending`. About 5–20 ms.
4. `test_flush_writes_at_once(qapp)`: `set('audio/gain', 2.5)`; `flush()` → on disk, `not store.pending`.
5. `test_each_change_restarts_the_wait(qapp, monkeypatch)`: `FLUSH_MS` patched to 40 before `SettingsStore()`.
   `set('audio/gain', 1.5)`; `time.sleep(0.025)` without processing events (so the timer can't fire);
   `set('audio/gain', 1.6)` → `store._flush_timer.remainingTime() > 25`. A restart puts it back near 40; without one
   it would be at most 15, because the sleep is a lower bound. Then `flush()` → `'gain=1.6'` on disk. About 25 ms,
   with no upper-bound timing that a slow machine could break.
6. `test_without_an_application_set_writes_at_once(monkeypatch)`: `monkeypatch.setattr(settings_store,
   '_app_exists', lambda: False)`; `set('audio/gain', 2.5)` → on disk at once, `not store.pending`. No `qapp`.
7. `test_clear_drops_a_pending_write(qapp, fast_flush)`: `set('audio/gain', 3.0)` → pending; `clear()` → `not
   pending`, `'gain' not in on_disk(store)`; then `processEvents()` + `time.sleep(0.001)` in a loop for
   `4 * fast_flush` ms → still no `gain` on disk. Without the stop in `clear()`, the timer would fire during that loop
   (the loop's duration is a lower bound, so a slow machine only makes it longer). About 20 ms.
8. `test_a_failed_write_is_logged_once_and_retried(tmp_path, qapp, caplog)`: `blocker = tmp_path / 'blocked'`,
   `blocker.write_text('')`; `QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(blocker))` (a file
   where the config folder should be; `_fresh_state` resets the path for the next test). `store = SettingsStore()`;
   `set('audio/gain', 2.5)`; `flush()`; `set('audio/gain', 3.5)`; `flush()` → exactly one WARNING on
   `pylzr.settings` containing `store.path`; `store.get('audio/gain') == 3.5`. Then `blocker.unlink()`; `flush()` →
   `'gain=3.5' in on_disk(store)` (retried with nothing new set). All behaviour verified in §1.
9. `test_a_store_freed_with_a_change_pending_writes_it(qapp)`: `store.set('audio/gain', 2.5)`; `path = store.path`;
   `del store`; `gc.collect()` → `'gain=2.5' in Path(path).read_text()`. Pins the `~QSettings` behaviour that Q13 and
   the Ctrl+C-in-`closeEvent` case rely on.

**Through the window**

10. `test_closing_right_after_a_change_writes_it_after_the_blackout(make_window, monkeypatch)`: the real `FLUSH_MS`
    (no events are processed, so the timer can't fire). `h = make_window()`; DMX mode
    (`settings_panel.set_control_mode('DMX')`); `settings_panel.set_gain(2.5)` → `w.store.pending` and
    `'gain=2.5' not in on_disk(w.store)`. Wrap `w.store.flush` (a plain Python attribute) to record
    `sum(p['data'] == bytes(512) for p in dmx_packets())` before calling the real one. Wrap `w.engine.shutdown` to
    record `'gain=2.5' in on_disk(w.store)` before calling the real one. `h.close()` → the flush saw ≥ 3 dark frames;
    the shutdown saw the gain on disk; afterwards `'gain=2.5' in on_disk(w.store)` and `not w.store.pending`. This is
    PLAN.md's "closed right after a change" check, on disk, together with the close order.

### 7.3 New tests: `tests/test_safety.py` (they reuse its `hooks`, `safety` and `raise_in_a_slot`)

Import: `from pylzr.gui import settings_store`.

11. `test_ctrl_c_quit_writes_pending_settings(hooks, make_window, qapp, monkeypatch)`: `FLUSH_MS` patched to `60_000`
    before `make_window`, so the timer can't be what writes it. As
    `test_ctrl_c_in_a_slot_closes_the_window_like_the_close_button` (install the hook with
    `on_interrupt=pylzr.__main__._quit_as_if_closed`, `w.show()`), then `w.settings_panel.set_gain(2.5)`;
    `raise_in_a_slot(KeyboardInterrupt())`; `wait_until(lambda: not w.isVisible())` →
    `'gain=2.5' in Path(w.store.path).read_text()` and `not w.store.pending`.
12. `test_settings_keep_saving_after_an_unhandled_exception(safety, make_window, qapp, monkeypatch)`: `FLUSH_MS`
    patched to 5 before `make_window`. `w = make_window(safety=safety).window`; `raise_in_a_slot()`;
    `w.settings_panel.set_gain(2.5)` → `wait_until(lambda: Path(w.store.path).exists() and 'gain=2.5' in
    Path(w.store.path).read_text(), timeout=1.0)` (Q1: the app keeps running and so does saving).

Count: 1379 − 1 (replaced) + 10 (7.2) + 2 (7.3) = **1390**.

Runtime: the store tests wait about 50 ms in all (#3 ≈ 5–20 ms, #5 ≈ 25 ms, #7 ≈ 20 ms; the rest don't wait). The
three window tests (#10–#12) cost about what any window test costs, 40–80 ms each (`--durations` from Task 3:
0.04–0.08 s). Expected total: about 0.2–0.3 s added to an 11–12 s suite, under the 0.5 s target. Checklist step 6
measures it (`--durations=0` on the new tests) and the result goes in `HANDOFF.md`. No test sleeps except the fixed
25 ms in #5, the bounded loop in #7, and `wait_until`'s polling.

---

## 8. Verification

```powershell
.venv\Scripts\python -m pytest tests/test_settings_store.py -q
.venv\Scripts\python -m pytest tests/test_safety.py tests/test_main_window_dmx.py tests/test_main_window.py -q
.venv\Scripts\python -m pytest -q                     # 1390 passed, nothing skipped; run 3 times
.venv\Scripts\ruff check .
git diff --exit-code -- tests/golden/                 # golden files unchanged
```

Timing tests 20 times in a row (they must pass every time), and their cost:
`for ($i=0; $i -lt 20; $i++) { .venv\Scripts\python -m pytest tests/test_settings_store.py tests/test_safety.py -q -k "flush_timer or written_once_on_flush or timer_writes or restarts or clear_drops or pending_settings or keep_saving or after_the_blackout" }`
`.venv\Scripts\python -m pytest tests/test_settings_store.py tests/test_safety.py -q --durations=0 -k "<the 12 new test names>"`:
the new tests together under 0.5 s.

Each guard must catch its regression (change, run, restore, and check `git diff` shows only the intended work):
- `_DeferredSettings.event` returning `super().event(event)` for every event → #1 and #2 fail (Qt writes on the next
  pass).
- `set()` calling `self._sync()` instead of starting the timer → #1 and #2 fail.
- the timer's `timeout` not connected to `flush` → #3 and #12 fail.
- `set()` starting the timer only when it isn't active (no restart) → #5 fails.
- removing `self.store.flush()` from `closeEvent` → #10 and #11 fail.
- moving it after `self.engine.shutdown()`, or before `self.dmx_out.stop()` → #10 fails.
- removing `self._flush_timer.stop()` from `clear()` → #7 fails.

Manual (not CI):
1. `python -m pylzr`; open Settings; note the mtime of the .ini file (path shown by `SettingsStore().path`; on
   Windows `%APPDATA%\PyLZR\PyLZR.ini`). Drag the gain slider back and forth for 5 s, release → the mtime changes
   once, about 0.4 s after release (PowerShell: `(Get-Item $env:APPDATA\PyLZR\PyLZR.ini).LastWriteTime` before,
   during and after).
2. Change gain and close the window within a second → reopen: the gain is restored.
3. Change gain and press Ctrl+C in the terminal within a second → reopen: restored.

---

## 9. Decisions this task depends on (all recorded in the design's Open questions)

- **Q13 (decided).** No extra flush on exit paths that skip `closeEvent`. Today no such path exists (§6). Pending
  changes would be written by `~QSettings` when the window is freed (7.2 #9 pins that). Reversible: one line in
  `main()`, `app.aboutToQuit.connect(window.store.flush)`. That signal fires before `exec_()` returns, so on a
  close-less quit the write would come before the `atexit` blackout, which is why it isn't added.
- **Q14 (decided).** Qt's automatic sync is held back with a `QSettings` subclass that ignores `UpdateRequest`,
  rather than by keeping pending values in a Python dict and calling `setValue()` only on flush. The subclass keeps
  every current behaviour: `get()` through Qt, cache sharing between stores, the destructor write and `clear()`. It
  needs no test changes beyond §7. It relies on how Qt implements the automatic sync (an `UpdateRequest` event to the
  `QSettings` object, Qt 5.15). The pinning tests 7.2 #1 and #2 fail if a Qt update changes that, and `ROADMAP.md`'s
  PyQt6 spike re-checks them. The dict alternative breaks the in-process sharing that ten existing tests rely on.
  Reversible: delete the class and use `QSettings`.
- **Q3 (decided).** `FLUSH_MS = 400`, with the "since input last paused" wording (§1).

---

## 10. Checklist

1. On `hayden/components-pt3` with a clean tree (apart from the docs from this planning step): `pytest -q` → 1379
   passed.
2. `src/pylzr/gui/settings_store.py`: the imports; `log`; `FLUSH_MS`; `_DeferredSettings`; `_app_exists`; the new
   docstring paragraph; `__init__`; `pending`; `set()`; `flush()`; `clear()`; `_sync()`, exactly as in §3.1.
3. `tests/test_settings_store.py`: the new imports, `FAST_MS`, the `on_disk` helper and the `fast_flush` fixture;
   replace `test_each_change_is_written_to_disk_immediately` (`:77-81`) with 7.2 #1–#9 in the store section; add #10
   at the end of the window section. Run `pytest tests/test_settings_store.py -q`. #10 fails until step 4.
4. `src/pylzr/gui/main_window.py`: the class docstring sentence and the `closeEvent` comment, and
   `self.store.flush()` right after `self._close_dmx_tester()` in `closeEvent` (§3.2). Run
   `pytest tests/test_settings_store.py tests/test_main_window_dmx.py tests/test_main_window.py -q`.
5. `tests/test_safety.py`: 7.3 #11 after `test_ctrl_c_in_a_slot_closes_the_window_like_the_close_button`, #12 after
   `test_switching_control_mode_after_the_stop_resumes_dmx`; import `settings_store` from `pylzr.gui`. Run
   `pytest tests/test_safety.py -q`.
6. Full suite 3 times (1390), the timing loop 20 times, the `--durations` check (new tests under 0.5 s together),
   the regression checks in §8 (restore each), `ruff check .`, golden unchanged.
7. Docs: the §1 fixes and the Q3/Q13/Q14 decisions are already in `PLAN.md`, `docs/design/safety-phase.md` and
   `ROADMAP.md`. If anything in steps 2–6 differed from this plan, update them to match. Mark Task 4 `— DONE` in
   `PLAN.md`; update `HANDOFF.md` (state, results including the measured runtime, next task: Task 5).
8. Manual checks 1–3 from §8 if the app can be run; otherwise say they weren't run.
9. Stop for review. Commit message:

    ```
    Debounced settings writes (P5)

    - SettingsStore writes the .ini file FLUSH_MS (400 ms) after the last
      change instead of on every set(), so dragging a slider writes once.
      Qt's own sync on the next event-loop pass is held back too; without
      a QCoreApplication set() still writes at once.
    - flush() writes now; the window calls it in closeEvent, right after
      the blackout and before audio shutdown, so a normal close and
      Ctrl+C keep the last change. clear() drops any pending write.
    - A failed write is logged once; the value is kept and written by the
      next successful sync.
    ```
