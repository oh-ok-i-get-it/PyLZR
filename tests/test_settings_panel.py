import pytest

from pylzr.gui import SettingsPanel


@pytest.fixture
def panel(qapp):
    return SettingsPanel()


def capture(signal):
    received = []
    signal.connect(lambda *args: received.append(args[0] if len(args) == 1 else args))
    return received


def test_audio_devices_select_current_and_emit_index(panel):
    received = capture(panel.audio_device_changed)
    panel.set_audio_devices([(3, 'Mic A'), (7, 'Mic B')], current_index=7)
    assert panel._device_combo.currentIndex() == 1
    assert received == []                       # populating doesn't emit
    panel._device_combo.setCurrentIndex(0)
    assert received == [3]


def test_unknown_current_device_selects_first(panel):
    panel.set_audio_devices([(3, 'Mic A'), (7, 'Mic B')], current_index=99)
    assert panel._device_combo.currentIndex() == 0


def test_long_names_are_truncated(panel):
    long_name = 'X' * 40
    panel.set_audio_devices([(0, long_name)], current_index=0)
    panel.set_midi_ports([long_name], long_name)
    for combo in (panel._device_combo, panel._midi_combo):
        assert combo.itemText(0) == 'X' * 30 + '…'


def test_midi_ports_select_current_and_emit_label(panel):
    received = capture(panel.midi_port_changed)
    panel.set_midi_ports(['A', 'B'], 'B')
    assert panel._midi_combo.currentIndex() == 1
    panel._midi_combo.setCurrentIndex(0)
    assert received == ['A']


def test_midi_ports_with_nothing_open_select_nothing(panel):
    panel.set_midi_ports(['A', 'B'], None)
    assert panel._midi_combo.currentIndex() == -1


def test_gain_and_smoothing_scaling(panel):
    gains, smooths = capture(panel.audio_gain_changed), capture(panel.smoothing_changed)
    panel._gain_slider.setValue(250)
    panel._smooth_slider.setValue(40)
    assert gains == [2.5] and smooths == [0.4]
    assert panel._gain_readout.text() == '250%'
    assert panel._smooth_readout.text() == '0.4'


@pytest.mark.parametrize('combo, signal, expected', [
    ('_window_combo', 'fft_window_changed', ['rectangle', 'hann', 'hamming', 'blackman']),
    ('_log_combo',    'log_level_changed',  ['info', 'debug', 'quiet']),
    ('_mode_combo',   'control_mode_changed', ['MIDI', 'DMX']),
])
def test_dropdown_values(panel, combo, signal, expected):
    received = capture(getattr(panel, signal))
    widget = getattr(panel, combo)
    for row in [*range(1, widget.count()), 0]:
        widget.setCurrentIndex(row)
    assert received == expected[1:] + expected[:1]


def test_window_dropdown_lists_every_fft_window(panel):
    from pylzr.analysis import FFTWorker
    combo = panel._window_combo
    assert [combo.itemData(i) for i in range(combo.count())] == list(FFTWorker.WINDOW_NAMES)
    assert combo.currentData() == 'rectangle'


def test_sound_mode_button(panel):
    received = capture(panel.app_sm_toggled)
    panel._sm_btn.click()
    assert len(received) == 1
    panel.sync_sound_mode(True)
    assert panel._sm_btn.isChecked() and panel._sm_btn.text() == 'ON'
    assert len(received) == 1                    # syncing doesn't emit


def test_status_indicators(panel):
    panel.set_midi_status(True, 'PyLZR-MIDI (virtual)')
    assert panel._midi_val.text() == 'PyLZR-MIDI (virtual)'
    panel.set_midi_status(False, 'Not connected')
    assert panel._midi_val.text() == 'Not connected'
    panel.set_audio_status(True, 'A' * 30)
    assert panel._audio_val.text() == 'A' * 24 + '…'
    panel.set_diagnostics(21.4, 3)
    assert panel._diag_fps.text() == '21 fps' and panel._diag_overflow.text() == '3'
