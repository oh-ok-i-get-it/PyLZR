from PyQt5.QtCore import Qt
from ..core import text_styles as txt
from ..core.app_logger import logger

_FIRST_NOTE = 60  # C3

# Keyboard keys in note order: the first key sends _FIRST_NOTE, each next key
# one semitone higher (60 → 107). Shift is not here: the main window uses it
# to toggle sound mode.
_KEYS = [
    (Qt.Key_1, '1'), (Qt.Key_2, '2'), (Qt.Key_3, '3'), (Qt.Key_4, '4'), (Qt.Key_5, '5'),
    (Qt.Key_6, '6'), (Qt.Key_7, '7'), (Qt.Key_8, '8'), (Qt.Key_9, '9'), (Qt.Key_0, '0'),
    (Qt.Key_Minus, '-'), (Qt.Key_Equal, '='), (Qt.Key_Tab, 'TAB'),
    (Qt.Key_Q, 'q'), (Qt.Key_W, 'w'), (Qt.Key_E, 'e'), (Qt.Key_R, 'r'), (Qt.Key_T, 't'),
    (Qt.Key_Y, 'y'), (Qt.Key_U, 'u'), (Qt.Key_I, 'i'), (Qt.Key_O, 'o'), (Qt.Key_P, 'p'),
    (Qt.Key_BracketLeft, '['), (Qt.Key_BracketRight, ']'),
    (Qt.Key_A, 'a'), (Qt.Key_S, 's'), (Qt.Key_D, 'd'), (Qt.Key_F, 'f'), (Qt.Key_G, 'g'),
    (Qt.Key_H, 'h'), (Qt.Key_J, 'j'), (Qt.Key_K, 'k'), (Qt.Key_L, 'l'),
    (Qt.Key_Semicolon, ';'), (Qt.Key_Apostrophe, "'"),
    (Qt.Key_Z, 'z'), (Qt.Key_X, 'x'), (Qt.Key_C, 'c'), (Qt.Key_V, 'v'),
    (Qt.Key_B, 'b'), (Qt.Key_N, 'n'), (Qt.Key_M, 'm'),
    (Qt.Key_Comma, ','), (Qt.Key_Period, '.'), (Qt.Key_Slash, '/'),
    (Qt.Key_Space, 'SPACE'), (Qt.Key_Return, 'ENTER'),
]

# Qt key code -> (MIDI note, display name)
_KEY_TO_NOTE = {int(key): (_FIRST_NOTE + i, name) for i, (key, name) in enumerate(_KEYS)}


class KeyboardMapper:
    """Routes Qt key codes to MIDI notes via a static lookup table.

    handle_key() is a no-op when sound mode is active (midi_out.sm_ON).
    """

    def __init__(self, midi_out):
        self._midi = midi_out

    def handle_key(self, key_num: int):
        if self._midi.sm_ON:
            return
        mapping = _KEY_TO_NOTE.get(key_num)
        if mapping is not None:
            note, name = mapping
            print(
                txt.B + txt.CYANB + txt.BLACK + 'Pressed:' +
                txt.RESET + txt.CYAN + txt.B + f' {name}' + txt.RESET
            )
            print(f'midi value: {note}')
            logger.info(f'Key: {name} → MIDI {note}', '#00bcd4')
            self._midi.press_note(note)
