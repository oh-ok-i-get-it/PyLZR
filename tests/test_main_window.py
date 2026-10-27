"""App-level behaviour of the main window, driven through its public surface
(keys, panel signals) with fake audio and MIDI."""

import gc

import pyaudio as fake_pyaudio
import rtmidi as fake_rtmidi
from PyQt5.QtCore import QPoint, Qt

from helpers import note_messages, tone_chunks, wait_for_note_offs, wait_until


def log_text(harness):
    return harness.window.log_panel._text.toPlainText()


# ── Startup / MIDI connection ────────────────────────────────────────────────

def test_startup_on_mac_uses_virtual_port(harness):
    sp = harness.window.settings_panel
    assert harness.window.midi_out.connected
    assert sp._midi_combo.currentText() == 'PyLZR-MIDI (virtual)'
    assert sp._midi_val.text() == 'PyLZR-MIDI (virtual)'
    assert 'MIDI: opened "PyLZR-MIDI (virtual)"' in log_text(harness)


def test_startup_on_windows_without_loopmidi(make_window):
    fake_rtmidi.reset('win')
    harness = make_window()
    sp = harness.window.settings_panel
    assert not harness.window.midi_out.connected
    assert sp._midi_combo.currentIndex() == -1
    assert sp._midi_val.text() == 'Not connected'
    assert log_text(harness).count('loopMIDI') == 1      # hint shown once


def test_windows_connects_when_loopmidi_appears_and_settings_opened(make_window):
    fake_rtmidi.reset('win')
    harness = make_window()
    fake_rtmidi.ports.append('PyLZR-MIDI 1')
    harness.window.controls._gear_btn.click()
    assert harness.window.midi_out.port_label == 'PyLZR-MIDI 1'
    assert harness.window.settings_panel._midi_combo.currentText() == 'PyLZR-MIDI 1'


def test_choosing_another_midi_port(harness):
    combo = harness.window.settings_panel._midi_combo
    combo.setCurrentIndex(combo.findText('IAC Driver Bus 1'))
    harness.key(Qt.Key_Q)
    wait_for_note_offs()
    assert fake_rtmidi.sent[-2:] == [('IAC Driver Bus 1', [0x90, 73, 112]),
                                     ('IAC Driver Bus 1', [0x80, 73, 0])]
    gc.collect()
    assert fake_rtmidi.live_virtual == []


# ── Keyboard and sound mode ──────────────────────────────────────────────────

def test_keyboard_notes_only_while_sound_mode_off(os_name, harness):   # os_name first: sets the OS before the window exists
    if os_name == 'win':
        fake_rtmidi.ports.append('PyLZR-MIDI 1')
        harness.window.controls._gear_btn.click()     # reconnect to loopMIDI
    harness.key(Qt.Key_Q)
    harness.key(Qt.Key_Shift)          # sound mode ON: keys ignored
    harness.key(Qt.Key_W)
    harness.key(Qt.Key_Shift)          # sound mode OFF again
    harness.key(Qt.Key_E)
    wait_for_note_offs()
    assert [m[1] for m in note_messages() if m[0] == 0x90] == [73, 75]


def test_sound_mode_buttons_stay_in_sync(harness):
    controls, settings = harness.window.controls, harness.window.settings_panel
    harness.key(Qt.Key_Shift)
    assert controls._sm_button.isChecked() and settings._sm_btn.isChecked()
    controls._sm_button.click()
    assert not controls._sm_button.isChecked() and not settings._sm_btn.isChecked()
    settings._sm_btn.click()
    assert controls._sm_button.isChecked() and settings._sm_btn.isChecked()
    assert harness.window.midi_out.sm_ON


def test_status_label_shows_last_key(harness):
    harness.key(Qt.Key_Q)
    assert harness.window.controls.status_label.text() == f'Key: q (code {int(Qt.Key_Q)})'


# ── Settings panel ───────────────────────────────────────────────────────────

def expected_panel_pos(window):
    gear = window.controls._gear_btn
    br = gear.mapTo(window, QPoint(gear.width(), gear.height()))
    return QPoint(max(0, br.x() - window.settings_panel.width()), br.y())


def test_settings_panel_opens_under_gear_and_follows_resize(harness, qapp):
    w = harness.window
    w.show()
    qapp.processEvents()
    w.controls._gear_btn.click()
    assert w.settings_panel.isVisible() and w.controls._gear_btn.isChecked()
    assert w.settings_panel.pos() == expected_panel_pos(w)

    w.resize(w.width() + 200, w.height())
    qapp.processEvents()
    assert w.settings_panel.pos() == expected_panel_pos(w)

    w.controls._gear_btn.click()
    assert not w.settings_panel.isVisible() and not w.controls._gear_btn.isChecked()


def test_audio_device_list_excludes_output_only_devices(harness):
    combo = harness.window.settings_panel._device_combo
    assert [combo.itemText(i) for i in range(combo.count())] == ['Fake Mic', 'Fake Line In']


def test_switch_audio_device(harness):
    w = harness.window
    old_stream = fake_pyaudio.streams[-1]
    w.settings_panel.audio_device_changed.emit(1)
    assert w.audio.device_name == 'Fake Line In'
    assert w.settings_panel._audio_val.text() == 'Fake Line In'
    assert old_stream.closed
    harness.feed(tone_chunks(2, (80, 400)))      # audio still flows
    assert len(harness.frames) == 2


def test_failed_audio_device_switch_keeps_old_device(harness):
    w = harness.window
    fake_pyaudio.fail_open.add(1)
    w.settings_panel.audio_device_changed.emit(1)
    assert w.audio.device_name == 'Fake Mic'
    assert w.settings_panel._audio_val.text() == 'Switch failed'
    assert 'Audio device switch failed' in log_text(harness)
    harness.feed(tone_chunks(2, (80, 400)))
    assert len(harness.frames) == 2


def test_log_level_filters_console(harness):
    w = harness.window
    w.settings_panel.log_level_changed.emit('quiet')
    before = log_text(harness)
    harness.key(Qt.Key_Q)
    assert log_text(harness) == before


def test_level_meter_tracks_input_when_settings_open(harness):
    w = harness.window
    w.show()                       # the meter only updates while the panel is visible
    w.controls._gear_btn.click()
    harness.feed(tone_chunks(1, (440, 16384)))
    assert 49 <= w.settings_panel._level_bar.value() <= 50


# ── Shutdown ─────────────────────────────────────────────────────────────────

def test_close_releases_audio_midi_and_fft_thread(harness):
    w = harness.window
    harness.close()
    gc.collect()
    assert fake_pyaudio.streams[-1].closed
    assert not w.midi_out.connected and fake_rtmidi.live_virtual == []
    wait_until(lambda: w.fft_thread.isFinished())
