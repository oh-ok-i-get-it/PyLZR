# Design: a non-GUI app object (D3 prep 2)

## Scope
One object owns the subsystems and their wiring: settings store, fixture library, MIDI output, node discovery, DMX
output, the cue switch, the audio engine, the keyboard mapper, the emergency stop. `MainWindow` becomes a view: it
builds panels, connects them to the app's signals and methods, and owns nothing that runs without a window. Out of
scope: a command-line interface (enabled, not built), moving anything onto another thread, changing any behaviour.

## Interfaces
```python
# src/pylzr/app.py
class App(QObject):
    """Everything PyLZR does that isn't a widget. Constructed once, before any window."""
    # Signals the GUI (or a CLI) listens to
    audio_status_changed   = pyqtSignal(bool, str)      # ok, detail (device name or error)
    audio_devices_changed  = pyqtSignal(list, int)      # [(index, name)], current index
    midi_ports_changed     = pyqtSignal(list, object)   # labels, current label or None
    midi_status_changed    = pyqtSignal(bool, str)
    control_mode_changed   = pyqtSignal(str)
    fixtures_changed       = pyqtSignal()               # library reloaded or patch saved: ask for types/patch/problems
    sound_mode_changed     = pyqtSignal(bool)
    # Pass-through objects the GUI reads from (no setters on them from the GUI side)
    store: SettingsStore; library: FixtureLibrary; engine: AudioEngine; dmx_out: DMXOutput
    midi_out: MIDIOutput; discovery: NodeDiscovery; output: OutputSwitch; safety: EmergencyStop

    def __init__(self, store: SettingsStore | None = None, safety: EmergencyStop | None = None)
    def start(self) -> None                 # restore saved settings into the subsystems, start the engine
    def shutdown(self) -> None              # the safety-phase order: dmx stop → tester-independent closes → dmx close

    # Commands (what today's MainWindow handlers do minus the widget updates)
    def set_control_mode(self, mode: str) -> None
    def set_node(self, ip: str, port_address: list[int]) -> bool
    def find_nodes(self) -> bool
    def switch_audio_device(self, index: int | None) -> bool
    def rescan_audio_devices(self) -> bool
    def open_midi_port(self, label: str | None) -> bool
    def toggle_sound_mode(self) -> bool
    def set_cutoff(self, band: str, mode: int, value: int) -> None
    def set_count_rate(self, frames: int) -> None
    def set_gain(self, gain: float) -> None
    def set_fft_window(self, name: str) -> None
    def set_log_level(self, level: str) -> None
    def reset_settings(self) -> None
    def reload_fixtures(self) -> None
    def save_patch(self, patch: Patch) -> None
    def key_pressed(self, qt_key: int) -> None
    def set_test_values(self, start: int, values: Sequence[int]) -> None
    def clear_test_values(self) -> None

# src/pylzr/gui/main_window.py
class MainWindow(QWidget):
    def __init__(self, app: App)            # builds panels, connects panel signals → app methods, app signals → setters
```
Ownership: `App` owns every subsystem and the `EmergencyStop` registrations. The settings-save wiring
(`main_window.py:162-171`) moves into `App` (the app saves what it applied, not what a widget emitted). Display-only
state (smoothing, the spectrum widget's EMA) stays in the window: `display/smoothing` is saved by the window through
`app.store`. The DMX tester window stays GUI-owned but drives `app.set_test_values`.

## Threading / timing
All on the GUI thread, as today. `App` is a `QObject` so its signals are queued correctly if a subsystem later moves
to a thread (D4's analysis worker). No new timers. `start()` must be called after the window has connected to the
signals, otherwise the restored settings are applied without being shown; `__main__` does: `app = App()`, `window =
MainWindow(app)`, `app.start()`, `window.show()`.

## Failure modes
| Failure | Safe state |
|---|---|
| A subsystem fails to construct (e.g. no audio device, audit P6, still out of scope) | `App.__init__` raises as today; `main()` logs and exits before any DMX is sent |
| `shutdown()` called twice (window close + atexit) | idempotent, like `engine.shutdown()` and `dmx_out.close()` today |
| A GUI setter raises while handling an app signal | exception hook → blackout; the app's state is already updated, so a later re-sync (`fixtures_changed`) repairs the view |
| `start()` never called (a test forgot) | nothing runs, nothing is sent |

## Migration (each step leaves the app working)
1. Create `App` holding exactly the objects `MainWindow.__init__` builds at `main_window.py:54-68`; `MainWindow`
   keeps attributes as aliases (`self.engine = app.engine`, …) so `tests/helpers.py:119` and the existing tests pass.
2. Move the handlers that touch no widget (`_on_control_mode_changed` minus the `set_tester_enabled` call,
   `_on_dmx_node_changed`, `_find_dmx_nodes`, `_on_audio_device_changed`, `_rescan_audio_devices`,
   `_on_midi_port_changed`, `_reset_settings` minus `_refresh_midi_ports`, `_on_patch_edited`,
   `main_window.py:227-324`) into `App` methods; the window's handlers call them and update widgets from the result or
   from the new signals.
3. Move `_apply_settings`/`_save_changes` (`main_window.py:149-171`) into `App.start()`; the window shows what the app
   applied by listening to the signals (the same path user input takes today).
4. Move the `EmergencyStop` registration and `closeEvent` order into `App.shutdown()`; `closeEvent` calls it.
5. `tests/test_app.py`: control mode, node, patch save, sound-mode toggle and shutdown order with no window; move the
   cases from `tests/test_main_window_dmx.py` that never look at a widget. Keep the window tests for the rest.
6. Drop the aliases once no test uses `window.<subsystem>` (the harness uses `window.app.engine`).

## Tests
CI only. The window tests are the regression guard for each step; the new `test_app.py` proves headless use. Add a
test that `App()` + `start()` + `shutdown()` sends no DMX in MIDI mode and the blackout sequence in DMX mode.

## Dependencies
Builds on the safety phase (ownership of the stop) and the cue abstraction (`output` is a `CueOutput` switch). The
frame clock and D3's scene player are created by `App`.

## Open questions
- **Q1.** Name: `App`, `Session`, or `Controller`? (`App` collides a little with `QApplication` in conversation.)
- **Q2.** Should the DMX tester's `set_rig` updates (`main_window.py:311-312`) go through `fixtures_changed`, or stay a
  direct call from the window? The signal is cleaner; the direct call is what exists.
- **Q3.** Is a headless `pylzr --no-gui` entry wanted in D3 (sound mode + scenes on a venue laptop with the window
  closed), or only the testability? Decides whether `App` gets its own console status output now.
- **Q4.** Keep `display/smoothing` with the window (a display setting) or move every saved key into `App` for one
  save path?
