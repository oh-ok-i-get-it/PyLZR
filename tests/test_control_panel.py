import pytest

from pylzr.gui import ControlPanel


@pytest.fixture
def panel(qapp):
    return ControlPanel()


def cutoff_sliders(panel, band):
    """Single access point for the private slider lists."""
    return panel._low_sliders if band == 'low' else panel._high_sliders


def cutoff_signal(panel, band):
    return panel.low_cutoff_changed if band == 'low' else panel.high_cutoff_changed


@pytest.mark.parametrize('band', ['low', 'high'])
def test_defaults(panel, band):
    assert [s.value() for s in cutoff_sliders(panel, band)] == [100, 300, 500]


@pytest.mark.parametrize('band', ['low', 'high'])
@pytest.mark.parametrize('mode, requested, expected', [
    (0, 50, 50),       # within range
    (0, 400, 300),     # Quiet can't exceed Mode 1
    (1, 50, 100),      # Mode 1 can't go below Quiet
    (1, 600, 500),     # ...or above Mode 2
    (1, 250, 250),
    (2, 200, 300),     # Mode 2 can't go below Mode 1
    (2, 20000, 20000),
])
def test_cutoffs_stay_ordered(panel, band, mode, requested, expected):
    emitted = []
    cutoff_signal(panel, band).connect(lambda m, v: emitted.append((m, v)))
    slider = cutoff_sliders(panel, band)[mode]
    slider.setValue(requested)
    assert slider.value() == expected
    assert emitted == [(mode, expected)]


def test_bands_are_independent(panel):
    cutoff_sliders(panel, 'low')[0].setValue(50)
    assert [s.value() for s in cutoff_sliders(panel, 'high')] == [100, 300, 500]


def test_sound_mode_button_emits_and_syncs(panel):
    emitted = []
    panel.sound_mode_toggled.connect(lambda: emitted.append(True))
    panel._sm_button.click()
    assert emitted == [True]
    panel.sync_sound_mode(True)
    assert panel._sm_button.isChecked() and panel._sm_button.text() == 'Sound Mode: ON'
    panel.sync_sound_mode(False)
    assert not panel._sm_button.isChecked() and panel._sm_button.text() == 'Sound Mode: OFF'


def test_gear_button_emits(panel):
    emitted = []
    panel.settings_toggled.connect(lambda: emitted.append(True))
    panel.gear_button.click()
    assert emitted == [True]


def test_mode_displays(panel):
    panel.update_sound_modes(-1, -1)
    assert panel._low_mode_display.text() == 'LOW\n—'
    panel.update_sound_modes(2, 3)
    assert panel._low_mode_display.text() == 'LOW\n2'
    assert panel._high_mode_display.text() == 'HIGH\n3'
    panel.update_dual_mode(2, 57)
    assert panel._dm_display.text() == 'DM\n2'
    assert panel._dm_count_display.text() == 'CNT\n57'
