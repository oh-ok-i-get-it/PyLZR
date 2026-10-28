import pytest
from PyQt5.QtCore import Qt

from pylzr.midi import KeyboardMapper

# Every mapped key in order; notes run sequentially from 60.
MAPPED_KEYS = [
    Qt.Key_1, Qt.Key_2, Qt.Key_3, Qt.Key_4, Qt.Key_5,
    Qt.Key_6, Qt.Key_7, Qt.Key_8, Qt.Key_9, Qt.Key_0,
    Qt.Key_Minus, Qt.Key_Equal, Qt.Key_Tab,
    Qt.Key_Q, Qt.Key_W, Qt.Key_E, Qt.Key_R, Qt.Key_T,
    Qt.Key_Y, Qt.Key_U, Qt.Key_I, Qt.Key_O, Qt.Key_P,
    Qt.Key_BracketLeft, Qt.Key_BracketRight,
    Qt.Key_A, Qt.Key_S, Qt.Key_D, Qt.Key_F, Qt.Key_G,
    Qt.Key_H, Qt.Key_J, Qt.Key_K, Qt.Key_L,
    Qt.Key_Semicolon, Qt.Key_Apostrophe,
    Qt.Key_Z, Qt.Key_X, Qt.Key_C, Qt.Key_V, Qt.Key_B, Qt.Key_N, Qt.Key_M,
    Qt.Key_Comma, Qt.Key_Period, Qt.Key_Slash,
    Qt.Key_Space, Qt.Key_Return,
]


class FakeMidiOut:
    def __init__(self, sound_mode_on=False):
        self.sm_ON = sound_mode_on
        self.notes = []

    def press_note(self, note):
        self.notes.append(note)


def make_mapper(sound_mode_on=False):
    """Single construction point — update here if the constructor changes."""
    out = FakeMidiOut(sound_mode_on)
    return KeyboardMapper(out), out


@pytest.mark.parametrize('index, key', list(enumerate(MAPPED_KEYS)))
def test_key_sends_its_note(index, key):
    mapper, out = make_mapper()
    mapper.handle_key(int(key))
    assert out.notes == [60 + index]


def test_keys_ignored_while_sound_mode_on():
    mapper, out = make_mapper(sound_mode_on=True)
    for key in MAPPED_KEYS:
        mapper.handle_key(int(key))
    assert out.notes == []


@pytest.mark.parametrize('key', [Qt.Key_F1, Qt.Key_Escape, Qt.Key_Backspace, Qt.Key_Control,
                                 Qt.Key_Shift])   # Shift toggles sound mode in the main window
def test_unmapped_keys_ignored(key):
    mapper, out = make_mapper()
    mapper.handle_key(int(key))
    assert out.notes == []
