import pytest

from pylzr.analysis import SoundMode

DEFAULT_CUTOFFS = (100, 300, 500)

# One average value safely inside each mode for the default cutoffs
AVG_FOR_MODE = {0: 50, 1: 200, 2: 400, 3: 600}

# (low_mode, high_mode) -> MIDI note with dual mode OFF. (0, 0) is "SPACE".
BASE_NOTES = {
    (0, 0): 106, (0, 1): 60, (0, 2): 61, (0, 3): 62,
    (1, 0): 63,  (1, 1): 64, (1, 2): 65, (1, 3): 66,
    (2, 0): 67,  (2, 1): 68, (2, 2): 69, (2, 3): 70,
    (3, 0): 71,  (3, 1): 72, (3, 2): 73, (3, 3): 74,
}
DUAL_MODE_OFFSET = 15


class RecordingOutput:
    def __init__(self):
        self.notes = []

    def press_note(self, note):
        self.notes.append(note)


def make_sound_mode(output, low=DEFAULT_CUTOFFS, high=DEFAULT_CUTOFFS, dm_toggle_rate=120):
    """Single construction point — update here if the constructor changes."""
    return SoundMode(low, high, output, dm_toggle_rate=dm_toggle_rate)


@pytest.mark.parametrize('value, mode', [
    (0, 0), (99.9, 0),
    (100, 1), (299.9, 1),    # a value equal to a cutoff belongs to the higher mode
    (300, 2), (499.9, 2),
    (500, 3), (1e9, 3),
])
def test_threshold_boundaries(value, mode):
    sm = make_sound_mode(RecordingOutput())
    sm.set_mode(value, value)
    assert (sm.low_mode, sm.high_mode) == (mode, mode)


@pytest.mark.parametrize('modes', sorted(BASE_NOTES))
@pytest.mark.parametrize('dual_mode_on', [False, True])
def test_note_for_every_mode_pair(modes, dual_mode_on):
    out = RecordingOutput()
    sm = make_sound_mode(out)
    if not dual_mode_on:
        sm.toggle_dm_mode()
    low_mode, high_mode = modes
    sm.check_mode(AVG_FOR_MODE[low_mode], AVG_FOR_MODE[high_mode])

    expected = BASE_NOTES[modes]
    if dual_mode_on and modes != (0, 0):      # SPACE is never shifted
        expected += DUAL_MODE_OFFSET
    assert out.notes == [expected]
    assert sm.dm_mode_label == (2 if expected != BASE_NOTES[modes] else 1)


def test_note_sent_only_when_mode_pair_changes():
    out = RecordingOutput()
    sm = make_sound_mode(out)
    for low, high in [(50, 50), (60, 70), (200, 50), (210, 40), (50, 50)]:
        sm.check_mode(low, high)
    assert out.notes == [106, 63 + DUAL_MODE_OFFSET, 106]


def test_sound_mode_switch_starts_off():
    assert make_sound_mode(RecordingOutput()).enabled is False


def test_dual_mode_starts_on_and_toggles_after_rate():
    sm = make_sound_mode(RecordingOutput(), dm_toggle_rate=3)
    assert sm.dm_on is True
    assert sm.dm_countdown == 3
    sm.advance_dm_counter()
    sm.advance_dm_counter()
    assert sm.dm_countdown == 1 and sm.dm_on is True
    sm.advance_dm_counter()
    assert sm.dm_on is False and sm.dm_countdown == 3


def test_dual_mode_toggle_rate_can_change():
    sm = make_sound_mode(RecordingOutput(), dm_toggle_rate=10)
    sm.set_dm_toggle_rate(2)
    sm.advance_dm_counter()
    sm.advance_dm_counter()
    assert sm.dm_on is False


@pytest.mark.parametrize('band', ['low', 'high'])
def test_set_cutoff_moves_threshold_for_one_band(band):
    sm = make_sound_mode(RecordingOutput())
    sm.set_cutoff(band, 1, 250)             # Mode 1 cutoff: 300 -> 250
    sm.set_mode(280, 280)
    changed, untouched = (sm.high_mode, sm.low_mode) if band == 'high' else (sm.low_mode, sm.high_mode)
    assert changed == 2
    assert untouched == 1
