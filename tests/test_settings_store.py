"""Saved settings: the store itself, and restore/save/reset through the window."""

from pathlib import Path

import pyaudio as fake_pyaudio
import pytest
import rtmidi as fake_rtmidi
from PyQt5.QtCore import QSettings, Qt

from pylzr.gui.settings_store import DEFAULTS, SettingsStore


# ── SettingsStore ────────────────────────────────────────────────────────────

def test_uses_the_test_folder_not_real_user_config(tmp_path):
    assert Path(SettingsStore().path).is_relative_to(tmp_path)


def test_empty_store_gives_defaults():
    store = SettingsStore()
    assert {key: store.get(key) for key in DEFAULTS} == DEFAULTS


def test_round_trip_survives_a_new_instance():
    values = {
        'cutoffs/low': [50, 250, 900], 'cutoffs/high': [10, 20, 30000],
        'analysis/count_rate': 35, 'analysis/fft_window': 'hann',
        'display/smoothing': 0.4, 'audio/gain': 2.5,
        'audio/device': 'Fake Line In', 'midi/port': 'IAC Driver Bus 1',
        'app/log_level': 'debug', 'app/control_mode': 'DMX',
        'dmx/node_ip': '192.168.1.250', 'dmx/port_address': [1, 2, 3],
    }
    store = SettingsStore()
    for key, value in values.items():
        store.set(key, value)
    reloaded = SettingsStore()
    assert {key: reloaded.get(key) for key in values} == values


def test_unreadable_values_fall_back_to_defaults():
    qs = QSettings(QSettings.IniFormat, QSettings.UserScope, 'PyLZR', 'PyLZR')
    qs.setValue('analysis/count_rate', 'not a number')
    qs.setValue('cutoffs/low', ['1', '2'])          # wrong length
    qs.sync()
    store = SettingsStore()
    assert store.get('analysis/count_rate') == DEFAULTS['analysis/count_rate']
    assert store.get('cutoffs/low') == DEFAULTS['cutoffs/low']


@pytest.mark.parametrize('key, bad', [
    ('app/control_mode', 'OSC'),                     # not a mode PyLZR has
    ('app/control_mode', 'dmx'),                     # case matters
    ('dmx/node_ip',      '10.201.6'),
    ('dmx/node_ip',      'node.local'),
    ('dmx/node_ip',      '::1'),                     # Art-Net is IPv4 only
    ('dmx/port_address', ['128', '0', '0']),         # net is 0–127
    ('dmx/port_address', ['0', '16', '0']),          # subnet is 0–15
    ('dmx/port_address', ['0', '0', '16']),          # universe is 0–15
    ('dmx/port_address', ['0', '0']),                # wrong length
    ('dmx/port_address', 'zero'),
])
def test_unusable_dmx_values_fall_back_to_defaults(key, bad):
    """e.g. a hand-edited PyLZR.ini"""
    qs = QSettings(QSettings.IniFormat, QSettings.UserScope, 'PyLZR', 'PyLZR')
    qs.setValue(key, bad)
    qs.sync()
    assert SettingsStore().get(key) == DEFAULTS[key]


def test_dmx_defaults():
    store = SettingsStore()
    assert store.get('app/control_mode') == 'MIDI'
    assert store.get('dmx/node_ip') == '10.201.6.100'
    assert store.get('dmx/port_address') == [0, 0, 0]


def test_each_change_is_written_to_disk_immediately():
    """Nothing is lost if the app is killed: the file is up to date after set()."""
    store = SettingsStore()
    store.set('audio/gain', 2.5)
    assert 'gain=2.5' in Path(store.path).read_text()


def test_clear():
    store = SettingsStore()
    store.set('audio/gain', 3.0)
    store.clear()
    assert SettingsStore().get('audio/gain') == 1.0


# ── Through the window ───────────────────────────────────────────────────────

def change_everything(w):
    """Change every saved setting the way a user would."""
    w.controls.set_cutoffs('low', [400, 600, 800])     # all above today's Mode 1: must not clamp
    w.controls.set_cutoffs('high', [50, 150, 250])
    w.controls.set_count_rate(30)
    panel = w.settings_panel
    panel.set_gain(2.0)
    panel.set_fft_window('hamming')
    panel.set_smoothing(0.5)
    panel.set_log_level('debug')
    panel._device_combo.setCurrentIndex(panel._device_combo.findData(1))        # Fake Line In
    panel._midi_combo.setCurrentIndex(panel._midi_combo.findData('IAC Driver Bus 1'))


def test_settings_restored_after_restart(make_window):
    first = make_window()
    change_everything(first.window)
    first.key(Qt.Key_Shift)                             # sound mode ON …
    first.close()

    w = make_window().window
    assert w.controls.cutoffs('low') == [400, 600, 800]
    assert w.controls.cutoffs('high') == [50, 150, 250]
    assert w.engine.analyzer.count_rate == 30
    assert w.engine.gain == 2.0
    assert w.settings_panel._window_combo.currentData() == 'hamming'
    assert w.spectrum_widget._smoothing == 0.5
    assert w.settings_panel._log_combo.currentData() == 'debug'
    assert w.engine.audio.device_name == 'Fake Line In'
    assert w.midi_out.port_label == 'IAC Driver Bus 1'
    assert not w.engine.sound_mode.enabled              # … but always starts OFF
    # restored cutoffs reached the analysis, not just the sliders
    w.engine.sound_mode.set_mode(500, 0)
    assert w.engine.sound_mode.low_mode == 1


def test_hand_edited_cutoffs_are_put_in_order(make_window):
    """Out-of-order or out-of-range saved cutoffs are sorted and clamped."""
    SettingsStore().set('cutoffs/low', [900, 100, 99999])
    w = make_window().window
    assert w.controls.cutoffs('low') == [100, 900, 40000]
    assert [s.value() for s in w.controls._cutoff_sliders['low']] == [100, 900, 40000]


def test_saved_audio_device_opened_directly(make_window):
    SettingsStore().set('audio/device', 'Fake Line In')
    make_window()
    assert [s.device_index for s in fake_pyaudio.streams] == [1]   # never opened the default first


def test_missing_saved_devices_fall_back_to_defaults(make_window):
    store = SettingsStore()
    store.set('audio/device', 'Unplugged USB Mic')
    store.set('midi/port', 'Unplugged Interface')
    w = make_window().window
    assert w.engine.audio.device_name == 'Fake Mic'
    assert w.midi_out.port_label == 'PyLZR-MIDI (virtual)'


def test_saved_loopmidi_port_missing_on_windows(make_window):
    fake_rtmidi.reset('win')
    SettingsStore().set('midi/port', 'PyLZR-MIDI 1')
    w = make_window().window
    assert not w.midi_out.connected                     # same as a fresh start without loopMIDI


def test_reset_to_defaults(make_window):
    w = make_window().window
    change_everything(w)
    w.settings_panel._reset_btn.click()

    assert w.controls.cutoffs('low') == DEFAULTS['cutoffs/low']
    assert w.controls.cutoffs('high') == DEFAULTS['cutoffs/high']
    assert w.engine.analyzer.count_rate == DEFAULTS['analysis/count_rate']
    assert w.engine.gain == 1.0
    assert w.settings_panel._window_combo.currentData() == 'rectangle'
    assert w.spectrum_widget._smoothing == 0.0
    assert w.settings_panel._log_combo.currentData() == 'info'
    assert w.engine.audio.device_name == 'Fake Mic'
    assert w.midi_out.port_label == 'PyLZR-MIDI (virtual)'
    store = SettingsStore()
    assert {key: store.get(key) for key in DEFAULTS} == DEFAULTS


def test_failed_device_switch_is_not_saved(make_window):
    w = make_window().window
    fake_pyaudio.fail_open.add(1)
    w.settings_panel.audio_device_changed.emit(1)
    assert SettingsStore().get('audio/device') == ''
