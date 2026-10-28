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


# ── Control mode + DMX ───────────────────────────────────────────────────

def test_control_modes_come_from_config(panel):
    from pylzr.core import CONTROL_MODES
    combo = panel._mode_combo
    assert tuple(combo.itemData(i) for i in range(combo.count())) == CONTROL_MODES
    assert [combo.itemText(i) for i in range(combo.count())] == ['MIDI', 'DMX (Art-Net)']
    assert 'not yet implemented' not in combo.toolTip()


def test_set_control_mode_emits_like_the_user(panel):
    received = capture(panel.control_mode_changed)
    panel.set_control_mode('DMX')
    panel.set_control_mode('DMX')               # unchanged: no second emit
    assert received == ['DMX']


def test_dmx_node_defaults(panel):
    assert panel._node_ip_edit.text() == '10.201.6.100'
    assert [s.value() for s in panel._port_spins] == [0, 0, 0]
    assert [(s.minimum(), s.maximum()) for s in panel._port_spins] == [(0, 127), (0, 15), (0, 15)]


def edit_ip(panel, text):
    """Type into the IP field and press Enter, as a user would."""
    edit = panel._node_ip_edit
    edit.setText(text)
    edit.editingFinished.emit()


def test_valid_ip_is_emitted_once(panel):
    received = capture(panel.dmx_node_changed)
    edit_ip(panel, '192.168.1.250')
    edit_ip(panel, '192.168.1.250')              # unchanged: no second emit
    assert received == [('192.168.1.250', [0, 0, 0])]


@pytest.mark.parametrize('typed', ['10.201.6', '10.201.6.', '300.1.1.1', ''])
def test_invalid_ip_reverts_to_the_last_good_one(panel, typed):
    received = capture(panel.dmx_node_changed)
    edit_ip(panel, typed)
    assert panel._node_ip_edit.text() == '10.201.6.100'
    assert received == []


def test_ip_field_only_accepts_ip_like_typing(panel):
    from PyQt5.QtGui import QValidator
    validator = panel._node_ip_edit.validator()
    assert validator.validate('10.20', 0)[0] == QValidator.Acceptable     # partial is fine while typing
    assert validator.validate('10.2x', 0)[0] == QValidator.Invalid
    assert validator.validate('1.2.3.4.5', 0)[0] == QValidator.Invalid


def test_universe_spins_emit_full_node(panel):
    received = capture(panel.dmx_node_changed)
    panel._port_spins[2].setValue(3)
    panel._port_spins[0].setValue(1)
    assert received == [('10.201.6.100', [0, 0, 3]), ('10.201.6.100', [1, 0, 3])]


def test_spin_change_while_ip_half_typed_keeps_last_good_ip(panel):
    received = capture(panel.dmx_node_changed)
    panel._node_ip_edit.setText('10.2')          # not finished yet
    panel._port_spins[1].setValue(2)
    assert received == [('10.201.6.100', [0, 2, 0])]


def test_set_dmx_node_emits_once_for_all_fields(panel):
    received = capture(panel.dmx_node_changed)
    panel.set_dmx_node('10.201.6.101', [1, 2, 3])
    assert received == [('10.201.6.101', [1, 2, 3])]
    panel.set_dmx_node('10.201.6.101', [1, 2, 3])
    assert len(received) == 1                    # same values: nothing to restore


def test_set_dmx_node_ignores_an_invalid_ip(panel):
    received = capture(panel.dmx_node_changed)
    panel.set_dmx_node('not an ip', [0, 0, 1])
    assert panel._node_ip_edit.text() == '10.201.6.100'
    assert received == [('10.201.6.100', [0, 0, 1])]


def test_tester_button(panel):
    received = capture(panel.dmx_tester_requested)
    assert not panel._tester_btn.isEnabled()     # MIDI mode at start
    assert 'Control Mode to DMX' in panel._tester_btn.toolTip()
    panel.set_dmx_tester_enabled(True)
    panel._tester_btn.click()
    assert len(received) == 1
    assert 'live' in panel._tester_btn.toolTip()


@pytest.mark.parametrize('state, colour', [
    ('off', '#383838'), ('sending', '#2ecc71'), ('warning', '#e3b341'), ('error', '#e74c3c'),
])
def test_dmx_status_dot(panel, state, colour):
    panel.set_dmx_status(state, 'detail')
    assert colour in panel._dmx_dot.styleSheet()
    assert panel._dmx_val.text() == 'detail'


def test_long_dmx_status_is_shortened_with_full_tooltip(panel):
    detail = 'via 192.168.176.169 — check cable / IP'
    panel.set_dmx_status('warning', detail)
    assert panel._dmx_val.text() == detail[:22] + '…'
    assert panel._dmx_val.toolTip() == detail


def test_dmx_status_defaults_to_off(panel):
    panel.set_dmx_status()
    assert panel._dmx_val.text() == 'Off'
