# Task 6: notice an audio stall (P4): implementation plan

Branch `hayden/components-pt3`, after the commit that adopted P4 and P6 as Tasks 6 and 7. Task text: `PLAN.md`,
Task 6. Design: `docs/design/safety-phase.md` (Interfaces, Threading, Failure modes, Migration step 6, Open questions
Q15–Q21, Later improvements). Audit: `docs/AUDIT.md` P4. Baseline: `pytest -q` gives **1391 passed** (13 Nov 2026,
14.0 s).

Decisions this task rests on (recorded in the design's Open questions; the code marks each where it applies):
- **Q15, decided:** a stall sends the quiet cue through sound mode, not the Task 3 emergency stop (§5).
- **Q16, decided:** `STALL_TIMEOUT_S = 2.0`, `STALL_CHECK_MS = 250`.
- **Q17, decided for now:** no automatic reopen; the warning points at ↻. Listed in the design's "Later
  improvements".
- **Q18, decided:** digital silence is sound, not a stall.
- **Q19, decided:** one WARNING per stall and one INFO per recovery, no rate limit.
- **ASSUMPTION(Q21), new in this revision:** no automatic SPACE goes out when SPACE is already the last note sent on
  the MIDI port (§2). To review with this plan.

Review changes (13 Nov 2026): SPACE consistency with Task 3's Q10–Q12 (§2, new tests #13–#17 and #31–#35); stall
messages that say what happened and what to do, checked in the in-app console (§3.2, test #29).

---

## 1. What the audit's fix misses (checked in this planning step)

The audit proposes: in `_report_diagnostics`, when `fps == 0` while `audio.is_active`, warn, turn the dot red, and
fall back to the quiet cue after N silent seconds. Reading the code shows these problems with doing it that way:

| Finding | Where | Consequence and fix |
|---|---|---|
| `fps` counts FFT results handled on the GUI thread (`_on_spectrum`), not chunks captured | `engine.py:177-178, 196-197` | After the GUI thread is blocked for a while, Qt may run the 1 s diagnostics timer before the queued chunks, so a busy GUI could look like a stall. **Fix:** stamp each chunk on PortAudio's callback thread, before it is queued (§3.2, `_on_audio_chunk`). |
| `audio.is_active` is `stream.is_active()` | `audio_input.py:88-90` | When PortAudio stops a stream by itself (device error), `is_active` turns False, and a check gated on it would miss the case that matters most. **Fix:** gate on "capture wanted" instead: the check timer runs from `engine.start()` to `engine.stop()`. |
| `time.monotonic()` on this machine is `GetTickCount64` (resolution 15.6 ms; counts time asleep) | `time.get_clock_info('monotonic')`, Python 3.12.10 | After the computer wakes, the gap since the last chunk includes the sleep, so the first check would declare a stall before PortAudio has had a chance to resume. **Fix:** a check that is itself over the timeout late restarts the wait (§3.1). The coarse resolution is also why recovery is detected by a chunk *counter*, not by comparing timestamps. |
| `check_mode(0, 0)` isn't always the quiet cue | `sound_mode.py:54-56` | With a cutoff set to 0, `bisect_right([0, …], 0)` is 1, not 0. **Fix:** an explicit `SoundMode.go_quiet()` (§3.3). |
| State from before the stall leaks into the cues after it | `engine.py:56, 128-130`; `analyzer.py:30-38` | Turning sound mode on during a stall would resend `_last_averages` (the music from before); and the analyzer's partly filled window would mix audio from before and after. **Fix:** clear `_last_averages` and `analyzer.reset()` on a stall (§3.2). |
| The quiet cue is SPACE, and Task 3 sends SPACE too | `sound_mode.py:27, 62`; `main_window.py:377-388` | A stall plus an emergency stop could send SPACE twice in a row (§2). **Fix:** one "last note" record at the MIDI port, checked by both (§2, §3.4–§3.7). |

Also: almost every window and engine in the suite lives for a while with no audio delivered. With a real 2 s timeout,
any test that runs past 2 s (a slow `wait_until`) would get a quiet cue in the middle of its note assertions. Every
test therefore runs with stalls off (`STALL_TIMEOUT_S = inf`, autouse fixture), and the stall tests turn them on
(§3.9, §7).

## 2. SPACE: consistent with Task 3's Q10–Q12

**What sound mode does today.** It already sends SPACE as its normal quiet cue. `SoundMode.MODE_MAP[0][0]` is
`MIDI_SPACE_NOTE` (106, `sound_mode.py:27`), and `update_mode` sends it with no dual-mode offset (`:62`), every time
the mode changes to LOW 0 / HIGH 0: every quiet passage in the music. `check_mode` sends only on a change of mode
(`:80-84`), so sound mode alone never sends SPACE twice in a row: a different cue always comes between. The two
exceptions are deliberate resends: `reset()` when sound mode is turned on (`engine.py:127-129`), and the keyboard's
SPACE key. The stall's quiet cue (`go_quiet` → `update_mode`) uses that same path and the same mode guard, so two
stalls with only quiet audio between them send SPACE once.

**Why the first plan wasn't safe enough.** The emergency stop's arm (Q10–Q12) counts only its own SPACE; it knows
nothing about sound mode's. So, in MIDI mode with sound mode on:
- stall (sound mode sends SPACE), then an exception: the stop is still armed and sends SPACE again, back to back;
- an exception (the stop sends SPACE) while the music is loud, then a stall: the mode is not 0 / 0, so `go_quiet`
  sends SPACE again. The same happens today when the music simply goes quiet after an emergency stop (Q6 lets cues
  keep flowing), so this is an existing gap that the stall makes likelier;
- sound mode turned off and on twice during a stall: `reset()` makes each `go_quiet` send.

If SoundSwitch toggles on SPACE, the second one turns the blackout look off.

**The rule (ASSUMPTION(Q21)).** No automatic SPACE goes out when SPACE is already the last note sent on the MIDI port.
- `MIDIOutput` records the last Note ON it sent (`last_note`), under its send lock, from `press_note` and `panic`.
  `open()` and `close()` reset it to None.
- `press_note(note, *, skip_if_last=False)`: with `skip_if_last`, it sends nothing when `note == last_note`. The check
  and the send are one step under the lock.
- `SoundMode.update_mode` sends the SPACE cue with `skip_if_last=True` (any cause: a quiet window, a stall, sound
  mode turned on); other cues go out as today.
- `panic(note)` skips `note` when it is already `last_note` (all-notes-off still goes out) and returns False, so the
  window keeps the arm set (Q11 as decided: the arm is used up only by a SPACE that reaches the port).
- Switching Control Mode to MIDI calls `midi_out.forget_last_note()` next to `_rearm_space()`, before the switch.
  Opening a port starts with None. So the rule holds within one MIDI enable and one port connection, exactly the
  scope of the arm (Q10, Q12), and the Task 3 tests that expect SPACE again after re-enabling MIDI keep passing.
- The keyboard never passes `skip_if_last`: a person pressing SPACE twice means it.

**Why not share the arm.** The arm is once per MIDI enable. If the stall's SPACE used it, a second stall hours later
(after the music came back and went away again) would send no quiet cue at all, and the laser would hold its look,
which is the failure this task is for. It also lives in the window, while the cue comes from the engine through the
output switch. The port is the one place every note to SoundSwitch passes, under a lock both threads already take.

**Result.** Stall then emergency stop, emergency stop then stall, two stalls, or sound mode toggled during a stall:
SPACE reaches SoundSwitch once. Two stalls with a lit cue between send SPACE after each lit cue, the same pattern as
two quiet passages in the music since v0.3. All-notes-off from a stop after a SPACE is unchanged from Task 3 (Q2: how
SoundSwitch treats controller 123 is unchecked; it isn't SPACE).

**Side effect to accept.** Sound mode turned off and on in quiet music no longer resends SPACE when SPACE was the last
note sent. SoundSwitch is already on that look.

## 3. Changes by file

### 3.1 `src/pylzr/audio/stall.py` (new, pure Python: no Qt, no numpy)

```python
"""Notices when audio stops arriving (audit P4, docs/design/safety-phase.md).

Pure Python, no Qt: PortAudio's callback thread calls chunk(), the owner's
thread calls check() on a timer and restart() when capture (re)starts.
Only missing chunks count, never their level: digital silence is sound
(design Q18).
"""

import time
from collections.abc import Callable
from typing import Literal

StallEvent = Literal['stalled', 'resumed']


class StallWatch:
    """Says once when no audio chunk has arrived for timeout_s, and once when
    one arrives again.

    Each field has one writer, so no lock is needed: chunk() (callback
    thread) writes _last_chunk and _chunks; check() and restart() (owner's
    thread) write everything else. A float or int store is atomic under the
    GIL. chunk() does two stores and can't raise or block, as PortAudio's
    callback needs.

    A check() that comes more than timeout_s after the previous one means
    the owner's thread (or the whole computer) was stopped: the wait starts
    again rather than counting that time as silence.
    """

    def __init__(self, timeout_s: float, clock: Callable[[], float] = time.monotonic):
        self._timeout = timeout_s
        self._clock = clock
        now = clock()
        self._last_chunk = now           # chunk() only
        self._chunks = 0                 # chunk() only
        self._wait_from = now            # check() / restart(): silence counts from the later of this and _last_chunk
        self._checked = now
        self._stalled = False
        self._chunks_at_stall = 0

    @property
    def timeout_s(self) -> float:
        return self._timeout

    @property
    def stalled(self) -> bool:
        return self._stalled

    def chunk(self) -> None:
        """A chunk arrived now. Any thread (PortAudio's callback)."""
        self._last_chunk = self._clock()
        self._chunks += 1

    def restart(self) -> bool:
        """Capture (re)started or a new stream opened: silence counts from now.
        Returns True if that ended a stall."""
        self._wait_from = self._checked = self._clock()
        was_stalled, self._stalled = self._stalled, False
        return was_stalled

    def check(self) -> StallEvent | None:
        """'stalled' the first time no chunk has arrived for timeout_s,
        'resumed' the first time one arrives after that, otherwise None."""
        chunks = self._chunks            # read before _last_chunk: a chunk arriving in between is then seen as recent
        last_chunk = self._last_chunk
        now = self._clock()
        late, self._checked = now - self._checked > self._timeout, now
        if self._stalled:
            if chunks != self._chunks_at_stall:
                self._stalled = False
                return 'resumed'
            return None
        if late:                         # asleep, or this thread was blocked: not evidence of silence
            self._wait_from = now
            return None
        if now - max(last_chunk, self._wait_from) >= self._timeout:
            self._stalled, self._chunks_at_stall = True, chunks
            return 'stalled'
        return None
```

`src/pylzr/audio/__init__.py`: `from .stall import StallEvent, StallWatch`; add both to `__all__`.

### 3.2 `src/pylzr/engine.py`

**Imports (`:6-13`):** `from .audio import AudioInput, StallWatch`.

**Constants (after `:17`):**

```python
# Audio stall (audit P4, docs/design/safety-phase.md Q16): no chunk for this
# long while capturing = the input has stopped; checked this often
STALL_TIMEOUT_S = 2.0
STALL_CHECK_MS  = 250
```

Both are read when used (`__init__`, `start()`), not bound as default arguments, so tests can patch them.

**Signal (after `:37`):**

```python
    audio_status_changed = pyqtSignal(bool, str)                          # ok, detail: (False, 'No audio') on a stall,
                                                                          # (True, device name) when audio is back
```

**Class docstring (`:21-30`):** add one sentence: "If chunks stop arriving for `STALL_TIMEOUT_S` while capturing,
it warns, reports `audio_status_changed(False, …)` and, with sound mode on, sends the quiet cue."

**`__init__` (`:42-73`):** before `self.audio = …` (`:47`):

```python
        self._stall = StallWatch(STALL_TIMEOUT_S)        # before the input: its callback stamps it
```

`:47-48` becomes `AudioInput(CHUNK, SAMPLE_RATE, on_chunk=self._on_audio_chunk, device_name=device_name)`. After the
diagnostics timer (`:72-73`):

```python
        self._stall_timer = QTimer(self)
        self._stall_timer.timeout.connect(self._check_audio)
```

**`start()` / `stop()` (`:77-84`):**

```python
    def start(self):
        """Start capturing audio, and watching that it keeps arriving."""
        self.audio.start()
        self._restart_stall_watch()
        self._diag_timer.start(1000)
        self._stall_timer.start(STALL_CHECK_MS)

    def stop(self):
        self.audio.stop()
        self._diag_timer.stop()
        self._stall_timer.stop()
```

**New property (after `stop`):**

```python
    @property
    def audio_stalled(self) -> bool:
        """No audio has arrived for STALL_TIMEOUT_S while capturing."""
        return self._stall.stalled
```

**`set_sound_mode` (`:127-130`):** the tail becomes

```python
        sm.reset()
        if self._stall.stalled:                     # no audio: the quiet cue, never the last one from before the stall
            sm.go_quiet()
            self.modes_updated.emit(sm.low_mode, sm.high_mode, sm.dm_mode_label, sm.dm_countdown)
        elif self._last_averages is not None:
            sm.check_mode(*self._last_averages)
            self.modes_updated.emit(sm.low_mode, sm.high_mode, sm.dm_mode_label, sm.dm_countdown)
```

(`_last_averages` is already None during a stall; the explicit branch is what sends the quiet cue. In MIDI mode the
port skips it if SPACE is already the last note, §2.)

**`switch_device` / `refresh_devices` (`:136-153`):** after the successful call, before `return True`:
`self._restart_stall_watch()`. A failed switch leaves the old stream and the watch as they were. A failed rescan
leaves no stream (`audio_input.py:116-122`); the watch keeps running, so 2 s later it reports "No audio". Task 7
replaces that with "No input device".

**New methods (a `# ── Audio stall ──` section after `_report_diagnostics`, `:196-201`):**

```python
    # ── Audio stall ────────────────────────────────────────────────────────

    def _on_audio_chunk(self, samples: np.ndarray, overflowed: bool):
        """PortAudio's callback thread: note that audio arrived, then queue it
        for _process_chunk. Stamped here, not in _process_chunk, so a busy GUI
        thread never looks like a stalled input."""
        self._stall.chunk()
        self._chunk_captured.emit(samples, overflowed)

    def _restart_stall_watch(self):
        """Capture started or a new stream opened: wait STALL_TIMEOUT_S afresh.
        Ends a stall without the 'sending sound again' line: the new stream
        shows itself by delivering, or stalls again."""
        if self._stall.restart():
            self.audio_status_changed.emit(True, self.audio.device_name)

    def _check_audio(self):
        """Every STALL_CHECK_MS while started, on this (GUI) thread."""
        event = self._stall.check()
        if event == 'stalled':
            self._on_stalled()
        elif event == 'resumed':
            self._on_resumed()

    def _on_stalled(self):
        """No audio for STALL_TIMEOUT_S. Design Q15: the quiet cue, as for
        silence, not the emergency stop: the stall ends by itself when audio
        returns, and DMX content doesn't follow cues yet. The cue goes first,
        then the displays and the log (as in _on_spectrum)."""
        self._last_averages = None                # turning sound mode on now must not resend the cue from before
        self.analyzer.reset()                     # the next window is new audio only
        sm = self.sound_mode
        if sm.enabled and sm.go_quiet():
            self.modes_updated.emit(sm.low_mode, sm.high_mode, sm.dm_mode_label, sm.dm_countdown)
        if self.measure_level:
            self.level_measured.emit(0.0, False)
        self.audio_status_changed.emit(False, 'No audio')
        quiet = ' Sound mode stays on its quiet cue until sound returns.' if sm.enabled else ''
        # Design Q17 (no automatic reopen: the user clicks ↻) and Q19 (once per stall)
        log.warning(f'Audio: no sound from "{self.audio.device_name}" for {self._stall.timeout_s:g} s: the input '
                    f'has stopped (unplugged, or its driver stopped). Check the audio interface and its cable, then '
                    f'click ↻ next to Device in Settings (⚙).{quiet}')

    def _on_resumed(self):
        log.info(f'Audio: "{self.audio.device_name}" is sending sound again.', extra={'tone': Tone.ON})
        self.audio_status_changed.emit(True, self.audio.device_name)
```

**Where the lines show.** `log` is `get_logger('engine')`, i.e. `pylzr.engine`, a child of `pylzr`
(`app_logger.py:19, 41-43`). The window adds the in-app console's handler to `pylzr` (`main_window.py:58-59`), so
both lines reach the console in the window, and the terminal through `configure_console_logging()`. The console's
handler starts at INFO (`log_panel.py:38`), the Settings default is `'info'` (`settings_store.py:48`), so both show
by default; the WARNING gets the console's warning icon and colour (`log_panel.py:17-18, 116-122`), the INFO line is
green (`Tone.ON`). With the console set to "Quiet" (`LEVELS['quiet']` hides everything, `app_logger.py:24`) neither
shows; that is the user's choice, and the Settings dot still does. The wording names the device, says what happened
and what to do: the ↻ button sits next to the "Device" dropdown in Settings (`settings_panel.py:249-268`, tooltip
"Rescan audio inputs"). `SoundMode.update_mode` also logs the cue it sends (`SoundMode: LOW=0 HIGH=0 | DualMode=1 |
MIDI=106`), so the warning doesn't repeat it.

### 3.3 `src/pylzr/analysis/sound_mode.py`

New method after `check_mode` (`:80-84`):

```python
    def go_quiet(self) -> bool:
        """The quiet cue (LOW 0 / HIGH 0: the SPACE note), as if the music had
        stopped, unless that is already the mode. For when audio stops
        arriving (docs/design/safety-phase.md Q15). Callers check `enabled`,
        as for check_mode(). Returns True if the cue was issued (a MIDI port
        whose last note is already SPACE skips it, Q21)."""
        if (self.low_mode, self.high_mode) == (0, 0):
            return False
        self.low_mode = self.high_mode = 0
        self.update_mode()
        return True
```

`update_mode` (`:58-72`), the send at `:70` becomes:

```python
        # SPACE is never sent twice in a row on its own (ASSUMPTION(Q21)): the
        # port skips it if it is already the last note (e.g. the emergency stop's)
        self._output.press_note(note, skip_if_last=note == MIDI_SPACE_NOTE)
```

The log line after it is unchanged (it reports the cue sound mode chose; a skipped send is logged by the port at
DEBUG).

### 3.4 `src/pylzr/midi/midi_output.py`

**`__init__` (`:46-57`):** after `self._send_lock` (`:57`):

```python
        self._last_note: int | None = None   # last Note ON sent on this port; under _send_lock (design Q21)
```

**New, after `default_port` (`:64-68`):**

```python
    @property
    def last_note(self) -> int | None:
        """The last Note ON sent on this port (press_note or panic), or None
        since the port was opened or forget_last_note() was called."""
        return self._last_note

    def forget_last_note(self):
        """MIDI was (re)enabled: treat SoundSwitch as having had nothing yet,
        as the emergency stop's SPACE arm does (design Q10, Q21)."""
        with self._send_lock:
            self._last_note = None
```

**`close()` (`:95-103`):** inside the `with self._send_lock:` block, after `close_port()`: `self._last_note = None`.
(`open()` calls `close()` first, so a new port starts at None.)

**`press_note` (`:105-119`):**

```python
    def press_note(self, note: int, *, skip_if_last: bool = False):
        """Note ON now, Note OFF 50 ms later. skip_if_last: send nothing if
        `note` is already the last note sent on this port (checked and sent as
        one step under the send lock, so the emergency stop on another thread
        can't slip in between; design Q21)."""
        out = self.midiout
        if out is None:
            return
        with self._send_lock:
            skipped = skip_if_last and note == self._last_note
            if not skipped:
                out.send_message([_NOTE_ON, note, _VELOCITY])
                self._last_note = note
        if skipped:
            log.debug(f'MIDI: note {note} not sent: it is already the last note sent')
            return
        …                                          # send_off as today
```

The log is outside the lock (Task 3's rule: nothing that can re-enter under a send lock). If `send_message` raises,
`_last_note` is not updated.

**`panic(note)` (`:121-153`):** under the lock, before building the messages that follow all-notes-off, drop `note`
when `note == self._last_note`; after a successful Note ON, `self._last_note = note`. Concretely, the messages list
is built after `acquire` instead of before (`:133-135` move inside the `try` at `:139`):

```python
            try:
                repeat = note is not None and note == self._last_note
                messages = [[_CONTROL_CHANGE, _ALL_NOTES_OFF, 0]]
                if note is not None and not repeat:
                    messages += [[_NOTE_ON, note, _VELOCITY], [_NOTE_OFF, note, 0]]
                for message in messages:
                    …                                      # as today
                    if message[0] == _NOTE_ON (sent):
                        self._last_note = note
```

The summary line after the release says which: `MIDI: emergency stop sent (all notes off; note 106 skipped: it was
already the last note sent)`. Returns False when skipped, so `MainWindow._midi_emergency_stop` re-arms (unchanged
code, `main_window.py:386-388`).

### 3.5 `src/pylzr/core/protocols.py:4-7`, `src/pylzr/core/output_switch.py:39-40`, `src/pylzr/dmx/dmx_output.py:296-297`

```python
# protocols.py
    def press_note(self, note: int, *, skip_if_last: bool = False) -> None: ...
    # skip_if_last: an output that can tell (MIDI) sends nothing if `note` is the last note it sent

# output_switch.py
    def press_note(self, note: int, *, skip_if_last: bool = False):
        self.current.press_note(note, skip_if_last=skip_if_last)

# dmx_output.py: accepts and ignores it (no SPACE look to toggle; D3's cue→scene is idempotent)
    def press_note(self, note: int, *, skip_if_last: bool = False):
```

`KeyboardMapper.handle_key` (`key_map.py:59`) is unchanged: the keyboard never skips.

### 3.6 `src/pylzr/gui/main_window.py`

- After `engine.diagnostics_updated.connect(self._on_diagnostics)` (`:125`):
  `engine.audio_status_changed.connect(self.settings_panel.set_audio_status)`.
  `SettingsPanel.set_audio_status(connected, detail)` (`settings_panel.py:398-401`) already has the right
  signature. The existing `_show_audio_device(ok=True)` calls after a successful switch, rescan or reset still set
  the dot green; `_restart_stall_watch` emits the same thing, so the two agree.
- `_on_control_mode_changed` (`:283-284`):

  ```python
        if mode == 'MIDI':
            self._rearm_space()                   # before select(): a stop in between still sees DMX, keeps the arm
            self.midi_out.forget_last_note()      # same boundary for the SPACE repeat check (design Q21)
  ```

  Not in `_rearm_space()` itself: that is also called by `_midi_emergency_stop` when SPACE was skipped (`:387-388`),
  where the last note must stay.
- Class docstring (`:40-43`): add "If audio stops arriving, the engine warns in the console, the Audio In dot turns
  red and sound mode goes quiet (not the emergency stop). Neither path sends SPACE when it is already the last note
  sent (design Q21)."

### 3.7 `src/pylzr/analysis/analyzer.py:21-37`

Rename `_reset` to `reset` (three places: `:21`, `:23`, `:37`) and give it a docstring: "Drop the partly filled
window: the next push() starts a new one." No test calls `_reset` (checked with grep).

### 3.8 Test doubles that implement `press_note`

`tests/test_engine.py:19`, `tests/test_sound_mode.py:24`, `tests/test_output_switch.py:10`: accept
`*, skip_if_last=False`. The sound-mode and switch doubles also record it (`self.skips.append(skip_if_last)`) for
tests #11 and #18. `tests/test_key_map.py:27` is unchanged (the keyboard never passes it).

### 3.9 `tests/conftest.py` (new autouse fixture after `_no_real_network`, `:79-91`)

```python
@pytest.fixture(autouse=True)
def _no_audio_stalls(monkeypatch):
    """Most windows and engines in the suite live a while with no audio
    delivered; a real stall check would send the quiet cue in the middle of
    unrelated tests. Stall tests turn it back on (tests/test_stall.py and the
    stall sections of the engine, window and safety tests)."""
    import pylzr.engine as engine
    monkeypatch.setattr(engine, 'STALL_TIMEOUT_S', math.inf)
```

(`import math` at the top.) With `inf`, `check()` never declares a stall or a late check; the 250 ms timer still runs,
so the timer path is exercised by every window test.

### 3.10 Docs

- `README.md:288` ("New audio inputs"): add "If the input stops (unplugged, or its driver stops), PyLZR says so in
  the console after 2 s, the Audio In dot in Settings turns red and Sound Mode goes to its quiet cue. Plug it back in
  and click ↻."
- `docs/AUDIT.md` P4 row: status `done (<hash>)`; `PLAN.md` Task 6: `— DONE`; `HANDOFF.md`: results.
- If anything in the design turns out wrong while building, fix `safety-phase.md` in the same commit and say so.

## 4. New and changed names

| Name | Where | Kind |
|---|---|---|
| `StallWatch`, `StallEvent` | `pylzr/audio/stall.py`, exported from `pylzr.audio` | new class, type alias |
| `StallWatch.chunk()`, `.restart() -> bool`, `.check() -> StallEvent \| None`, `.stalled`, `.timeout_s` | same | new |
| `STALL_TIMEOUT_S = 2.0`, `STALL_CHECK_MS = 250` | `pylzr/engine.py` | new constants |
| `AudioEngine.audio_status_changed(bool, str)` | same | new signal (the name `app-object.md` already uses on `App`) |
| `AudioEngine.audio_stalled` | same | new property |
| `AudioEngine._on_audio_chunk`, `_restart_stall_watch`, `_check_audio`, `_on_stalled`, `_on_resumed`, `_stall`, `_stall_timer` | same | new private |
| `SoundMode.go_quiet() -> bool` | `pylzr/analysis/sound_mode.py` | new method |
| `AudioAnalyzer.reset()` | `pylzr/analysis/analyzer.py` | renamed from `_reset` |
| `MIDIOutput.last_note`, `MIDIOutput.forget_last_note()`, `MIDIOutput._last_note` | `pylzr/midi/midi_output.py` | new |
| `press_note(note, *, skip_if_last=False)` | `NoteOutput`, `OutputSwitch`, `MIDIOutput`, `DMXOutput` | new keyword |
| `MIDIOutput.panic(note)` | same | skips `note` when it is `last_note` |
| `_no_audio_stalls` | `tests/conftest.py` | new autouse fixture |
| `FakeClock`, `watch_with` | `tests/helpers.py` | new test helpers |

## 5. Threading and timing

| What | Thread | When |
|---|---|---|
| `StallWatch.chunk()` | PortAudio's callback thread | every chunk (46 ms), before the chunk is queued; two stores |
| `_check_audio()` → `StallWatch.check()` | GUI thread (engine's), `QTimer` | every 250 ms from `start()` to `stop()` |
| quiet cue (`go_quiet` → `OutputSwitch.press_note`) | GUI thread | inside `_check_audio`, the same thread `_on_spectrum` sends cues from, so `SoundMode` is never used from two threads |
| `restart()` | GUI thread | `start()`, after a successful `switch_device` / `refresh_devices` |
| `last_note` check and send | whichever thread sends: GUI (`press_note`), any (`panic`) | under `MIDIOutput._send_lock`, one step |

- **Detection time:** the stall is declared on the first check at least 2.0 s after the later of the last chunk and
  the last restart: 2.0–2.25 s after the last chunk, plus however long the GUI thread delays the timer.
- **Recovery time:** the first check after the first new chunk: ≤ 250 ms. The chunk itself is analysed as soon as
  it arrives, stall or not; recovery only changes the status and the log.
- **No false stall from a busy GUI:** the stamp comes from the callback thread, which never waits for the GUI. While
  the GUI thread is blocked the check can't run; when it runs, the stamp is fresh (chunks kept arriving). If the
  block lasted over 2 s, the check is late and restarts the wait anyway.
- **StallWatch races:** `check()` reads `_chunks` before `_last_chunk`. A chunk arriving between the two reads then
  makes `_last_chunk` recent, so no stall is declared on it. A chunk arriving right after both reads is counted at
  the next check: as recovery if a stall was just declared (`_chunks_at_stall` holds the count read before it).
  Every field has one writer (§3.1).
- **SPACE races:** the stall's quiet cue (GUI thread) and the emergency stop (any thread, e.g. the FFT thread) both
  read and write `_last_note` only under the MIDI send lock, together with their send, so whichever runs second sees
  the first's SPACE. `panic()` still waits at most 0.1 s for the lock (Task 3); if it gives up, it sends nothing at
  all (unchanged), so it can't add a SPACE either. `forget_last_note()` runs on the GUI thread before
  `output.select('MIDI')`, the same order as the arm, so a stop between them sees DMX or a forgotten note, never a
  half state that sends SPACE twice.
- **What happens to the cue and DMX:** with sound mode on, one quiet cue unless already quiet, and in MIDI mode none
  if SPACE is already the last note on the port; nothing else is sent. DMX: `DMXOutput.press_note` only logs at
  DEBUG today (no scenes), so DMX frames don't change at all; the timer keeps streaming the universe (base layer dark,
  tester overrides if open). After D3 the quiet cue reaches DMX through the cue→scene map; what a stall should do
  then is open (`d3-scenes.md` Q6).
- **Why not the Task 3 emergency stop (Q15):** (1) it is for an unknown program state, and after it DMX stays
  stopped until the user switches Control Mode; a stall is a known outside condition that should end by itself when
  the audio returns. (2) The quiet cue is what real silence sends, so it is the look the operator chose for "no
  music". In MIDI it is the same SPACE note the emergency stop would send, without all-notes-off and without using
  up the SPACE arm. (3) In DMX mode today the only DMX content is the tester's override layer, and someone testing
  the laser with no microphone plugged in must not be blacked out by it. An exception inside `_check_audio` still
  goes through the exception hook and triggers the emergency stop, as for any slot.

## 6. Edge cases

1. **Device unplugged.** Either the callbacks just stop (MME, CoreAudio) or PortAudio ends the stream
   (`is_active` turns False, WASAPI). Both are a stall: the check depends only on chunks arriving while the engine
   is started. PortAudio doesn't reopen a device by itself; plugging it back needs ↻ (rescan reopens it by name,
   `audio_input.py:107-126`) or choosing it. Both restart the watch; its chunks then show it working. No automatic
   reopen (Q17; a later improvement in the design).
2. **Sleep and wake.** `GetTickCount64` counts time asleep, so the first check after waking is late by the sleep
   and restarts the wait. If the stream survived, chunks arrive and nothing is reported. If it didn't, the stall is
   declared 2 s after wake. On macOS `time.monotonic()` stops while asleep: the gap is invisible, and the same 2 s
   applies after wake.
3. **Very quiet input vs. no input.** Quiet input still produces chunks, so it isn't a stall: sound mode sends the
   quiet cue through the normal path when the window's averages fall under the first cutoffs. Only missing callbacks
   count. A driver that keeps calling back with zeros after an unplug therefore gets the quiet cue (zeros are
   quiet) but no warning (Q18).
4. **Recovery when audio comes back.** The first chunk is analysed at once. The analyzer was reset at the stall, so
   the first window after it holds only new audio, and since sound mode sits at 0 / 0, that window's cue is sent if
   it isn't quiet. The INFO line and the green dot follow within 250 ms.
5. **Already quiet when it stalls.** `go_quiet()` returns False: no cue, no `modes_updated`. The warning still goes
   out.
6. **Sound mode off.** No cue (keyboard cues are in charge), warning (without the sound-mode sentence) and red dot as
   usual. Turning sound mode on while stalled issues the quiet cue (`set_sound_mode`, §3.2), never the cue from before
   the stall, and the port skips it if SPACE is already the last note.
7. **Stall and emergency stop together, two stalls, toggles during a stall:** SPACE once (§2).
8. **Keyboard cues during a stall.** Unaffected: with sound mode off they work (a SPACE key press always sends); with
   it on they're blocked, as today.
9. **Device switch or rescan while stalled.** A successful one ends the stall at once (dot green with the new
   name); if the new stream is silent too, the stall comes back 2 s later: a new WARNING, and no new cue (already
   quiet). A failed switch changes nothing. A failed rescan leaves no stream, so a stall is reported 2 s later if
   one wasn't already (Task 7 changes this to "No input device").
10. **Settings reset** (`_reset_settings` → `switch_device(None)`): same as a switch.
11. **A device that keeps dropping out.** One WARNING and one INFO per dropout, at most a pair every ~2 s (Q19).
12. **Startup.** `start()` restarts the watch, so the first stall can't come sooner than 2 s after start; devices
    that take a moment to deliver their first chunk (Bluetooth) have that long.
13. **Shutdown.** `engine.shutdown()` → `stop()` stops the check timer before the stream is closed, so closing the
    app never reports a stall. The stall state isn't cleared, which doesn't matter after shutdown.
14. **`engine.stop()` then `start()` while stalled** (tests only): `start()`'s restart ends the stall and emits
    `audio_status_changed(True, …)`.
15. **Emergency stop in force in DMX mode** (DMX panicked): the quiet cue goes to `DMXOutput.press_note`, a DEBUG
    line. The stall changes nothing about the panic.
16. **Displays.** The waveform and spectrum hold their last frame; FFT fps shows 0 in Performance; the level meter
    is set to 0 if it's showing. The console line shows whether Settings is open or not; the dot is in Settings.
17. **Console set to "Quiet".** Neither line shows (the user hid everything); the dot still does.
18. **FFT thread stuck while chunks arrive.** Not a stall (chunks are arriving); out of scope, as in the audit.
19. **`check()` and `chunk()` can't raise:** both are stores and arithmetic. `_on_audio_chunk` runs where an
    exception would be swallowed by PyAudio, so it holds nothing that can fail besides the existing `emit`.
20. **A MIDI send that raises** in `press_note`: `_last_note` keeps its old value (assigned after the send), so a later
    SPACE isn't wrongly skipped.

## 7. Tests

`tests/helpers.py` (after `wait_until`) gets the fake clock and a helper that swaps an engine's watch for a
fake-clock one and stops the real check timer, so only the test calls `_check_audio()`:

```python
class FakeClock:
    """time.monotonic stand-in: tests move time on by hand."""
    def __init__(self, t: float = 1000.0):
        self.t = t
    def __call__(self) -> float:
        return self.t
    def advance(self, seconds: float):
        self.t += seconds


def watch_with(engine, clock: FakeClock, timeout: float = 2.0) -> FakeClock:
    """Give `engine` a stall watch on `clock`; the test calls engine._check_audio() itself."""
    engine._stall_timer.stop()
    engine._stall = StallWatch(timeout, clock=clock)
    return clock


def stall(engine, clock: FakeClock):
    """Declare a stall now: 2 s of fake time with no chunks, then one check."""
    clock.advance(2.0)
    engine._check_audio()
```

### 7.1 Existing tests

- `test_turning_sound_mode_on_before_any_audio_sends_nothing` and the golden pipeline test pass because stalls are
  off (`inf`). The golden note sequence never has SPACE twice in a row (checked: 11 Note ONs, 3 of them 106, none
  adjacent), so `skip_if_last` changes nothing in it.
- `test_chunks_from_the_audio_thread_are_processed_in_order` still holds: `_on_audio_chunk` only adds a stamp before
  the same queued emit.
- Task 3's SPACE tests in `tests/test_safety.py` (`:408-510`) keep passing unchanged: each re-enable (Control Mode to
  MIDI, a port opened) forgets the last note, and `test_dmx_mode_stop_sends_no_midi_and_keeps_space_armed` never
  sent SPACE before. They are the guard that the forget sits at the arm's boundaries.
- The three test doubles in §3.8 accept the keyword.

### 7.2 New: `tests/test_stall.py` (pure, `FakeClock`)

1. `test_no_stall_while_chunks_arrive`: a chunk every 0.046 s and a check every 0.25 s for 10 s: `check()` never
   returns an event, `stalled` stays False.
2. `test_stall_is_declared_once_after_the_timeout`: no chunks after construction; checks at 0.25 s steps: None up to
   1.75 s, `'stalled'` at 2.0 s, None at every later check; `stalled` True.
3. `test_the_first_chunk_after_a_stall_resumes`: stall, then `chunk()`, then `check()` → `'resumed'`; `stalled`
   False; the next check → None; with no more chunks a new stall comes 2 s after that chunk.
4. `test_a_late_check_restarts_the_wait`: check at 0.25 s, then the next check 5 s later with no chunks → None (not
   `'stalled'`); then checks every 0.25 s: `'stalled'` first at 2.0 s after the late check, not before.
5. `test_a_late_check_keeps_a_stall`: stalled, then a check 5 s later with no chunks → None and still stalled; then
   `chunk()` and a check → `'resumed'`.
6. `test_restart_ends_a_stall_and_waits_afresh`: stalled; `restart()` → True, `stalled` False; checks every 0.25 s:
   `'stalled'` again at 2.0 s after the restart. `restart()` when not stalled → False.
7. `test_a_chunk_between_the_two_reads_counts_as_recent`: a subclass in the test turns `_chunks` into a property;
   armed just before `check()`, its getter returns the count and then calls `chunk()` once (a chunk arriving between
   `check()`'s two reads). Clock 2.5 s after the last chunk: `check()` → None, because the stamp read after the
   counter is new. Fails if the two reads are swapped (it then declares a stall that chunk should have prevented).
8. `test_an_infinite_timeout_never_stalls`: `StallWatch(math.inf)`, 10⁶ s with no chunks and late checks → None
   every time (pins the conftest fixture's mechanism).

### 7.3 New: `tests/test_sound_mode.py` (append after `:110`)

9. `test_go_quiet_sends_space_once`: `check_mode` into LOW 2 / HIGH 0 with dual mode on (note 82 sent); `go_quiet()`
   → True, `output.notes[-1] == 106` (no dual-mode offset), modes (0, 0), `dm_mode_label == 1`; a second
   `go_quiet()` → False and nothing more sent.
10. `test_go_quiet_after_reset_sends`: after `reset()` (modes −1, −1), `go_quiet()` → True and sends 106; and with a
    LOW cutoff of 0, `check_mode(0, 0)` is not LOW 0 but `go_quiet()` still is (the reason it exists, §1).
11. `test_only_the_space_cue_asks_the_port_not_to_repeat_it`: for every mode pair (both dual-mode states), the double
    records `skip_if_last` True for 106 and False for every other note.

### 7.4 New: `tests/test_analyzer.py` (append after `:36`)

12. `test_reset_drops_the_partial_window`: `count_rate=4`; push three frames, `reset()`, push four frames: the
    result is the average of the last four only, and nothing came back before the fourth.

### 7.5 New: `tests/test_midi_output.py` (section `# ── Last note (design Q21) ──` after the panic tests)

13. `test_last_note_is_the_last_note_on_sent`: None at first; `press_note(64)` → 64; `panic(106)` → 106;
    `panic()` (all-notes-off only) → still 106; `forget_last_note()` → None; `press_note(64)` then `close()` → None;
    `open()` again → None. A `send_message` that raises on `press_note(70)` leaves it at the previous note.
14. `test_skip_if_last_skips_only_a_repeat`: `press_note(106, skip_if_last=True)` twice → one Note ON;
    `press_note(82)` then `press_note(106, skip_if_last=True)` → sent; `press_note(106)` twice without the flag →
    two Note ONs (the keyboard's path).
15. `test_panic_skips_its_note_when_it_is_already_the_last_note`: `press_note(106)`; `panic(106)` → returns False,
    sent messages after that are `[ALL_OFF]` only; then `press_note(82)`, `panic(106)` → True, SPACE on and off.
16. `test_panic_and_a_skipping_press_on_two_threads_send_space_once` (deterministic): the open port's
    `send_message` is wrapped so that, on the main thread's SPACE Note ON (`press_note(106, skip_if_last=True)`),
    it starts a thread running `panic(106)` and `join(0.05)`s it before sending (with the lock, the panic is still
    waiting). Afterwards exactly one SPACE Note ON was sent, and `panic` returned False. Fails if the check moves
    outside the lock.

### 7.6 New: `tests/test_output_switch.py` (append)

17. `test_skip_if_last_is_forwarded_to_the_active_output`: `switch.press_note(106, skip_if_last=True)` → the MIDI
    double records `(106, True)`; a plain `press_note(60)` records `(60, False)`.

### 7.7 New: `tests/test_engine.py` (section `# ── Audio stall ──` after `:189`)

A `stalls` fixture on top of `engine`: `watch_with(engine, FakeClock())`, plus a recorder for
`audio_status_changed`.

18. `test_a_stall_sends_the_quiet_cue_once`: sound mode on; feed 20 chunks of `(80, 400)` (cue 82); `stall()` →
    `notes == [82, 106]` (with `skip_if_last=True` on the 106), status `[(False, 'No audio')]`, `audio_stalled`, one
    WARNING containing `no sound from "Fake Mic" for 2 s` and `Sound mode stays on its quiet cue`. Advance 5 × 0.25 s
    with a check each: no more notes, statuses or warnings.
19. `test_a_stall_when_already_quiet_sends_nothing`: sound mode on; feed 20 near-silent chunks (amplitude 1;
    averages ≈ 1.3 / 0.13) → cue 106 from the window; stall → `notes == [106]` still, one WARNING.
20. `test_a_stall_with_sound_mode_off_only_warns`: feed 20 chunks with sound mode off; stall → no notes; WARNING
    without the sound-mode sentence; status as in #18.
21. `test_audio_back_after_a_stall`: stall (as #18); feed 20 chunks of `(80, 400)`; `_check_audio()` → status
    `(True, 'Fake Mic')` last, one INFO `"Fake Mic" is sending sound again`, `not audio_stalled`,
    `notes == [82, 106, 82]` (the first window after the stall sends its cue).
22. `test_a_stall_drops_the_partial_window`: feed 20 chunks of `(80, 400)` → averages A; feed 10 loud chunks
    `(440, 30000)`; stall; feed 20 chunks of `(80, 400)` → exactly one new average, equal to A. Fails without
    `analyzer.reset()` (the window would mix 10 loud and 10 quiet chunks).
23. `test_turning_sound_mode_on_during_a_stall_sends_the_quiet_cue`: feed 20 chunks of `(80, 400)` with sound mode
    off (`_last_averages` set); stall; `set_sound_mode(True)` → `notes == [106]`, not `[82]`; `modes_updated` with
    0, 0.
24. `test_a_busy_gui_thread_is_not_a_stall`: advance 1.9 s; deliver 3 chunks from this thread with
    `fake_pyaudio.deliver` *without* processing events (they're queued, `engine.frames` unchanged); advance 1.9 s
    more; `_check_audio()` → not stalled, no status. Then process events: 3 frames. Fails if the stamp moves to
    `_process_chunk`.
25. `test_starting_switching_or_rescanning_restarts_the_wait` (parametrised: `stop+start`, `switch_device(1)`,
    `refresh_devices()`): sound mode on; stall; do the action (for `stop+start`, stop the real check timer again
    after `start()`) → status `(True, <device>)`, `not audio_stalled`; advance 1.9 s, check → still not stalled;
    advance 0.1 s, check → stalled again, a second WARNING, no new note (already quiet).
26. `test_the_check_timer_finds_a_stall_by_itself` (real clock, real timer): monkeypatch `STALL_TIMEOUT_S = 0.2` and
    `STALL_CHECK_MS = 20`, build a fresh `AudioEngine` (its own fixture, shut down afterwards), `start()`, deliver
    nothing: `wait_until(lambda: eng.audio_stalled, timeout=2)`; then deliver one chunk:
    `wait_until(lambda: not eng.audio_stalled)`. About 0.3 s.

### 7.8 New: `tests/test_main_window.py` (section `# ── Audio stall ──` after `:216`)

27. `test_an_audio_stall_turns_the_dot_red_and_back`: window (mac, virtual MIDI port); `watch_with(w.engine,
    FakeClock())`; stall → `settings_panel._audio_val.text() == 'No audio'`, `_audio_dot.styleSheet() == _IND_OFF`.
    Feed one chunk, `_check_audio()` → text `'Fake Mic'`, dot `_IND_ON`.
28. `test_an_audio_stall_sends_space_to_soundswitch`: Shift (sound mode on); feed one window of `(80, 400)`; stall →
    the last Note ON on the port is 106.
29. `test_stall_warning_and_recovery_show_in_the_console`: the window's console at its default level (assert the
    Settings log dropdown reads `Info`); stall → `log_text(harness)` contains `no sound from "Fake Mic" for 2 s`,
    `Check the audio interface` and `click ↻ next to Device in Settings`, and the console's document gains exactly
    one warning icon (`toHtml()` count of `pylzr-icon:triangle-alert` goes up by one). Feed a chunk and check: the
    console contains `"Fake Mic" is sending sound again.`

### 7.9 New: `tests/test_main_window_dmx.py` (append after `:298`)

30. `test_an_audio_stall_leaves_dmx_alone`: DMX mode; sound mode on; `w.dmx_out.set_test_values(1, [255])` (what the
    tester's sliders call; channels are 1-based); stall (fake clock as #27) → `w.dmx_out.active`,
    `not w.safety.triggered`, and the next frames sent (`wait_until` on two more packets) still have 255 on channel
    1; no dark frame among them.

### 7.10 New: `tests/test_safety.py` (section `# ── Audio stall and SPACE (design Q21) ──` after `:510`)

Each test: MIDI mode, mac virtual port, sound mode on (Shift), `watch_with(w.engine, FakeClock())`. Note Ons are read
with `note_ons()`, messages with `note_messages()`.

31. `test_a_stall_then_an_emergency_stop_send_space_once`: one window of `(80, 400)` (82); stall (SPACE);
    `w.safety.trigger('t')` → the messages it adds are `[ALL_OFF]` only; SPACE Note ONs: 1; the arm is still set
    (`w._space_armed`). A second `trigger` straight away → `[ALL_OFF]` only again. Then a lit window (82) and the
    audio is back; `trigger` again → ALL_OFF, SPACE on, SPACE off. Note Ons overall: `[82, 106, 82, 106]`.
32. `test_an_emergency_stop_then_a_stall_send_space_once`: a lit window (82); `trigger` → ALL_OFF, SPACE; stall →
    no new Note ON (the port skipped it); the mode display shows LOW 0 / HIGH 0. Note Ons: `[82, 106]`.
33. `test_two_stalls_with_quiet_audio_between_send_space_once`: lit window (82); stall (SPACE); one window of
    near-silent audio and a check (resumed, mode stays 0 / 0); stall again → Note Ons `[82, 106]`, two WARNINGs.
34. `test_two_stalls_with_a_lit_cue_between_send_space_after_each`: lit window (82); stall (SPACE); a lit window (82,
    resumed); stall again → Note Ons `[82, 106, 82, 106]`: SPACE never twice in a row; the second stall still goes
    quiet (why the arm isn't shared, §2).
35. `test_sound_mode_toggled_during_a_stall_sends_space_once`: lit window (82); stall (SPACE); Shift, Shift, Shift,
    Shift (off, on, off, on) → Note Ons `[82, 106]`.

New test ids: #1–#35, with #25 three cases: **37**. Expected suite: 1391 + 37 = **1428**. Added time: under 1 s
(#26 is ~0.3 s; the rest use the fake clock).

## 8. Verification

```
uv run pytest tests/test_stall.py tests/test_sound_mode.py tests/test_analyzer.py tests/test_midi_output.py tests/test_output_switch.py tests/test_engine.py tests/test_main_window.py tests/test_main_window_dmx.py tests/test_safety.py -q
uv run pytest tests/test_pipeline_golden.py -q
uv run pytest -q          # three runs in a row; 1428 passed each time
uv run ruff check .
git status --short tests/golden          # empty
uv run pytest -q --durations=0 tests/test_stall.py tests/test_engine.py tests/test_safety.py -k "stall or quiet or busy or restarts or space"   # added time
for i in $(seq 20); do uv run pytest -q tests/test_engine.py -k check_timer_finds || break; done    # the real-timer test, 20 runs
for i in $(seq 20); do uv run pytest -q tests/test_midi_output.py -k two_threads || break; done      # the two-thread SPACE test, 20 runs
```

Regression checks (each change undone afterwards, `git diff` then shows only the task's work):

| Remove or break | Must fail |
|---|---|
| Stamp in `_process_chunk` instead of `_on_audio_chunk` | #24 |
| No `analyzer.reset()` in `_on_stalled` | #22 |
| No `_last_averages = None` and no stalled branch in `set_sound_mode` | #23 |
| The late-check branch in `check()` | #4 |
| `check()` reads `_last_chunk` before `_chunks` | #7 |
| `go_quiet()` without its already-quiet guard | #9, #19 |
| No `_restart_stall_watch()` in `switch_device` / `refresh_devices` / `start` | #25 (the matching case) |
| The window connection to `set_audio_status` | #27 |
| The stall warning logged at DEBUG instead of WARNING | #29 |
| `update_mode` without `skip_if_last` for SPACE | #11, #32, #35 |
| `panic()` not checking `_last_note` | #15, #31 |
| The `skip_if_last` check outside the send lock | #16 |
| `forget_last_note()` missing from `_on_control_mode_changed` | `test_switching_control_mode_to_midi_rearms_space`, `test_a_stop_during_the_switch_to_midi_sends_space` (Task 3) |
| `forget_last_note()` placed in `_rearm_space()` instead | #31 (the skipped SPACE's re-arm would forget the last note, so the second stop sends SPACE right after the stall's) |

Manual checks (you; not run from here, they need the hardware):
1. MIDI mode with SoundSwitch, sound mode on, music playing; pull the USB microphone: within ~2 s the in-app console
   shows the warning with its icon, Settings shows a red "No audio", SoundSwitch gets SPACE. Plug it back, click ↻:
   "is sending sound again", dot green, cues resume.
2. Same, then trigger an emergency stop during the stall (a test build that raises in a handler, as in Task 3's
   manual check): SoundSwitch stays on its blackout look; a MIDI monitor shows one SPACE.
3. Sleep the laptop for a minute with PyLZR running and wake it: either nothing is reported (audio resumed) or one
   stall 2 s after wake; no warning during the sleep itself.
4. DMX mode with the tester open on the Gruolin; pull the microphone: the laser keeps the tester's look.
5. Whether SPACE latches or toggles in SoundSwitch (Q10's manual check) is still worth knowing; nothing here depends
   on it.

## 9. Checklist

1. [ ] `tests/helpers.py`: `FakeClock`, `watch_with`, `stall`. `tests/test_stall.py` #1–#8 (fail: no module).
2. [ ] `src/pylzr/audio/stall.py` + export in `audio/__init__.py`. #1–#8 pass.
3. [ ] `analyzer.py`: `_reset` → `reset`; #12.
4. [ ] `protocols.py`, `output_switch.py`, `dmx_output.py`: the `skip_if_last` keyword; the three test doubles
       (§3.8); #17.
5. [ ] `midi_output.py`: `_last_note`, `last_note`, `forget_last_note`, `close`, `press_note`, `panic`; #13–#16.
6. [ ] `sound_mode.py`: `go_quiet`, `skip_if_last` for SPACE in `update_mode`; #9–#11.
7. [ ] `tests/conftest.py`: `_no_audio_stalls`. Full suite. Expect two Task 3 tests to fail between step 5 and step 9
       (`test_switching_control_mode_to_midi_rearms_space`, `test_a_stop_during_the_switch_to_midi_sends_space`):
       `panic()` now skips a repeat, and the forget on Control Mode comes in step 9. Nothing else may fail.
8. [ ] `engine.py`: constants, signal, `_stall` before `AudioInput`, `_on_audio_chunk`, timer, `start`/`stop`,
       `audio_stalled`, `set_sound_mode`, restarts in `switch_device`/`refresh_devices`, the stall section with the
       final wording, docstring. Tests #18–#26.
9. [ ] `main_window.py`: the status connection, `forget_last_note()` in `_on_control_mode_changed`, the docstring;
       #27–#29; `test_main_window_dmx.py` #30; `test_safety.py` #31–#35 and Task 3's SPACE tests.
10. [ ] Design references in the code comments: Q15 and Q17/Q19 in `_on_stalled`, Q16 at the constants, Q18 in
        `stall.py`'s module docstring, `ASSUMPTION(Q21)` in `update_mode`, `press_note` and `panic`.
11. [ ] README line (§3.10).
12. [ ] §8: targeted tests, golden, suite ×3, ruff, `tests/golden` unchanged, durations, 20 runs each of #26 and #16,
        the regression table.
13. [ ] `docs/AUDIT.md` P4 row (status and hash once committed), `PLAN.md` Task 6 `— DONE`, `HANDOFF.md` (results,
        anything that differed from this plan), the design if anything in it was wrong.
14. [ ] Stop for review with a commit message.

## 10. Decisions and open questions

Recorded in `docs/design/safety-phase.md`, Open questions:
- **Q15, decided.** Quiet cue, not the emergency stop, and no DMX change (§5).
- **Q16, decided.** 2 s timeout, 250 ms checks.
- **Q17, decided for now.** No automatic reopen after a stall; the user clicks ↻. "Reopen the input automatically
  after a stall" is listed under the design's "Later improvements".
- **Q18, decided.** Digital silence isn't a stall; only missing callbacks are.
- **Q19, decided.** One WARNING per stall, one INFO per recovery, no rate limit.
- **ASSUMPTION(Q21), to review.** No automatic SPACE when SPACE is already the last note sent on the port, within
  the arm's boundaries (§2). Reversible: drop `skip_if_last` from `update_mode` and the check in `panic()`.

Elsewhere:
- `d3-scenes.md` **Q6**, open: what a stall does in DMX mode once scenes drive the laser (hold, quiet scene, or
  blackout). Nothing in this task depends on it.
- The dot that turns red lives in Settings; the console line is what shows with Settings closed. A main-window
  indicator would be new GUI and isn't in this task.
