import logging

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtCore import Qt, QPoint

from ..core import WINDOW_W, WINDOW_H
from ..core.app_logger import LOGGER_NAME, Tone, get_logger
from ..engine   import AudioEngine
from ..midi     import MIDIOutput, KeyboardMapper
from .spectrum_widget import SpectrumWidget
from .control_panel   import ControlPanel
from .settings_panel  import SettingsPanel
from .log_panel       import LogPanel, AvgPanel
from .settings_store  import DEFAULTS, SettingsStore

log = get_logger('app')


class MainWindow(QWidget):
    """Top-level application window: builds the panels and wires them to the
    AudioEngine (audio → analysis → sound mode) and the MIDI output.

    This class only connects things — the pipeline lives in engine.py and
    the audio/, analysis/ and midi/ packages. User settings are restored from
    the SettingsStore at startup and saved whenever they change.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle('PyLZR : SSP3CTRUM')
        self.setGeometry(100, 100, WINDOW_W, WINDOW_H)

        # Console first, so subsystem startup messages show in it
        self.log_panel = LogPanel()
        logging.getLogger(LOGGER_NAME).addHandler(self.log_panel.log_handler)

        self.store = SettingsStore()

        # Subsystems (saved devices are opened directly, falling back to defaults)
        self.midi_out = MIDIOutput()
        self._open_saved_midi_port()
        self.engine   = AudioEngine(self.midi_out, parent=self,
                                    device_name=self.store.get('audio/device') or None)
        self.key_map  = KeyboardMapper(self.midi_out, is_blocked=lambda: self.engine.sound_mode.enabled)

        # GUI panels
        self.spectrum_widget = SpectrumWidget(self.engine.bands)
        self.controls        = ControlPanel()
        self.avg_panel       = AvgPanel()

        bottom_row = QHBoxLayout()
        bottom_row.addWidget(self.log_panel, stretch=3)
        bottom_row.addWidget(self.avg_panel, stretch=1)

        layout = QVBoxLayout()
        layout.addWidget(self.controls)
        layout.addWidget(self.spectrum_widget)
        layout.addLayout(bottom_row)
        self.setLayout(layout)

        # Settings panel floats over the window as a child widget (no layout slot)
        self.settings_panel = SettingsPanel(self)
        self.settings_panel.hide()

        # Populate settings panel with live subsystem data
        self._show_audio_device(ok=True)
        self._refresh_midi_ports()
        self.settings_panel.set_dmx_status()

        # Engine → displays
        engine = self.engine
        engine.waveform_ready.connect(self.spectrum_widget.update_waveform)
        engine.spectrum_ready.connect(self.spectrum_widget.update_spectrum)
        engine.averages_ready.connect(self.avg_panel.append_avgs)
        engine.modes_updated.connect(self._on_modes_updated)
        engine.level_measured.connect(self.settings_panel.set_level)
        engine.diagnostics_updated.connect(self._on_diagnostics)

        # Control panel → engine
        self.controls.count_rate_changed.connect(engine.set_count_rate)
        self.controls.cutoff_changed.connect(engine.sound_mode.set_cutoff)
        self.controls.sound_mode_toggled.connect(self._toggle_sound_mode)
        self.controls.settings_toggled.connect(self._toggle_settings)

        # Settings panel → engine / outputs
        self.settings_panel.audio_device_changed.connect(self._on_audio_device_changed)
        self.settings_panel.audio_gain_changed.connect(engine.set_gain)
        self.settings_panel.midi_port_changed.connect(self._on_midi_port_changed)
        self.settings_panel.fft_window_changed.connect(engine.set_fft_window)
        self.settings_panel.smoothing_changed.connect(self.spectrum_widget.set_smoothing)
        self.settings_panel.log_level_changed.connect(self._on_log_level_changed)
        self.settings_panel.app_sm_toggled.connect(self._toggle_sound_mode)
        self.settings_panel.control_mode_changed.connect(self._on_control_mode_changed)
        self.settings_panel.reset_requested.connect(self._reset_settings)
        self.settings_panel.audio_devices_refresh_requested.connect(self._rescan_audio_devices)

        # Restore saved settings through the panels (same path as user input),
        # then save every later change
        self._apply_settings(self.store.get)
        self._save_changes()

        engine.start()

    # ------------------------------------------------------------------
    # Saved settings
    # ------------------------------------------------------------------

    def _open_saved_midi_port(self):
        saved = self.store.get('midi/port')
        if saved and saved in self.midi_out.list_ports():
            self.midi_out.open(saved)

    def _apply_settings(self, get):
        """Set every saved control from get(key) (stored or default values)."""
        self.controls.set_cutoffs('low',  get('cutoffs/low'))
        self.controls.set_cutoffs('high', get('cutoffs/high'))
        self.controls.set_count_rate(get('analysis/count_rate'))
        panel = self.settings_panel
        panel.set_gain(get('audio/gain'))
        panel.set_fft_window(get('analysis/fft_window'))
        panel.set_smoothing(get('display/smoothing'))
        panel.set_log_level(get('app/log_level'))

    def _save_changes(self):
        store, controls, panel = self.store, self.controls, self.settings_panel
        controls.cutoff_changed.connect(lambda band, _mode, _val: store.set(f'cutoffs/{band}', controls.cutoffs(band)))
        controls.count_rate_changed.connect(lambda v: store.set('analysis/count_rate', v))
        panel.audio_gain_changed.connect(lambda v: store.set('audio/gain', v))
        panel.fft_window_changed.connect(lambda v: store.set('analysis/fft_window', v))
        panel.smoothing_changed.connect(lambda v: store.set('display/smoothing', v))
        panel.log_level_changed.connect(lambda v: store.set('app/log_level', v))
        # Devices are saved in their handlers, once the switch has succeeded

    def _reset_settings(self):
        self._apply_settings(lambda key: DEFAULTS[key])
        if self.engine.switch_device(None):
            self._show_audio_device(ok=True)
        default_port = self.midi_out.default_port()
        if self.midi_out.port_label != default_port:
            self.midi_out.open(default_port)
        self._refresh_midi_ports()
        self.store.clear()
        log.info('Settings reset to defaults', extra={'tone': Tone.MUTED})

    # ------------------------------------------------------------------
    # Engine → display handlers
    # ------------------------------------------------------------------

    def _on_modes_updated(self, low_mode: int, high_mode: int, dm_label: int, dm_countdown: int):
        self.controls.update_sound_modes(low_mode, high_mode)
        self.controls.update_dual_mode(dm_label, dm_countdown)

    def _on_diagnostics(self, fps: float, overflows: int):
        if self.settings_panel.isVisible():
            self.settings_panel.set_diagnostics(fps, overflows)

    # ------------------------------------------------------------------
    # Control panel handlers
    # ------------------------------------------------------------------

    def _toggle_sound_mode(self):
        is_on = self.engine.toggle_sound_mode()
        self.controls.sync_sound_mode(is_on)
        self.settings_panel.sync_sound_mode(is_on)

    def _toggle_settings(self):
        visible = not self.settings_panel.isVisible()
        if visible:
            self._refresh_midi_ports()
            self._position_settings_panel()
            self.settings_panel.raise_()
        self.settings_panel.setVisible(visible)
        self.engine.measure_level = visible   # level meter only while it's shown
        self.controls.sync_gear(visible)

    def _position_settings_panel(self):
        """Right-align the floating settings panel under the gear button."""
        gear = self.controls.gear_button
        bottom_right = gear.mapTo(self, QPoint(gear.width(), gear.height()))
        self.settings_panel.move(max(0, bottom_right.x() - self.settings_panel.width()), bottom_right.y())

    # ------------------------------------------------------------------
    # Settings panel handlers
    # ------------------------------------------------------------------

    def _on_audio_device_changed(self, device_index: int):
        if self.engine.switch_device(device_index):
            self._show_audio_device(ok=True)
            self.store.set('audio/device', self.engine.audio.device_name)
        else:
            self.settings_panel.set_audio_status(False, 'Switch failed')

    def _rescan_audio_devices(self):
        if self.engine.refresh_devices():
            self._show_audio_device(ok=True)
        else:
            self.settings_panel.set_audio_status(False, 'Rescan failed')

    def _show_audio_device(self, ok: bool):
        audio = self.engine.audio
        self.settings_panel.set_audio_status(ok, audio.device_name)
        self.settings_panel.set_audio_devices(audio.get_input_devices(), audio.device_index)

    def _refresh_midi_ports(self):
        # Retry the default port while disconnected, e.g. loopMIDI started after PyLZR
        if not self.midi_out.connected:
            self.midi_out.open(self.midi_out.default_port())
        self.settings_panel.set_midi_ports(self.midi_out.list_ports(), self.midi_out.port_label)
        self.settings_panel.set_midi_status(self.midi_out.connected, self.midi_out.port_name)

    def _on_midi_port_changed(self, label: str):
        if self.midi_out.open(label):
            self.store.set('midi/port', label)
        self._refresh_midi_ports()

    def _on_log_level_changed(self, level: str):
        self.log_panel.set_level(level)
        log.info(f'Log level: {level}', extra={'tone': Tone.MUTED})

    def _on_control_mode_changed(self, mode: str):
        if mode == 'DMX':
            log.info('Control mode: DMX selected (not yet implemented)', extra={'tone': Tone.NOTICE})

    # ------------------------------------------------------------------
    # Qt event overrides
    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        if self.settings_panel.isVisible():
            self._position_settings_panel()
        super().resizeEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        if event.isAutoRepeat():   # a held key acts once
            return
        if event.key() == Qt.Key_Shift:  # either Shift key — toggle sound mode
            self._toggle_sound_mode()
        else:
            self.key_map.handle_key(event.key())
        self.controls.status_label.setText(f'Key: {event.text()} (code {event.key()})')
        super().keyPressEvent(event)

    def closeEvent(self, event):
        self.engine.shutdown()
        self.midi_out.close()
        logging.getLogger(LOGGER_NAME).removeHandler(self.log_panel.log_handler)
        super().closeEvent(event)
