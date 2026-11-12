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


def test_dmx_section_is_its_own_widget(panel):
    """Tested on its own in test_dmx_settings.py."""
    from pylzr.gui import DMXSettings
    assert isinstance(panel.dmx, DMXSettings)
    assert panel.dmx.parent() is panel


@pytest.mark.parametrize('state, colour', [
    ('off', '#383838'), ('connected', '#2ecc71'), ('sending', '#58a6ff'), ('warning', '#e3b341'),
    ('error', '#e74c3c'),
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


def test_clip_badge_follows_clipping(panel):
    assert panel._clip_lbl.property('state') == 'off'
    panel.set_level(1.0, clipping=True)
    assert panel._clip_lbl.property('state') == 'on'
    panel.set_level(0.5)
    assert panel._clip_lbl.property('state') == 'off'


def test_only_the_status_dots_carry_inline_styles(panel):
    from PyQt5.QtWidgets import QWidget
    dots = {panel._audio_dot, panel._midi_dot, panel._dmx_dot}
    styled = [w for w in panel.findChildren(QWidget) if w.styleSheet() and w not in dots]
    assert styled == [] and not panel.styleSheet()


def test_long_names_keep_the_full_name_as_tooltip(panel):
    from PyQt5.QtCore import Qt
    long_name = 'Focusrite USB Audio (Scarlett 2i2 4th Gen)'
    panel.set_audio_devices([(0, long_name)], current_index=0)
    assert panel._device_combo.itemData(0, Qt.ToolTipRole) == long_name
    assert panel._device_combo.full_text() == long_name
