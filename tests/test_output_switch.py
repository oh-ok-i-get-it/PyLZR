import pytest

from pylzr.core.output_switch import OutputSwitch


class Recorder:
    def __init__(self):
        self.notes = []

    def press_note(self, note):
        self.notes.append(note)


@pytest.fixture
def midi():
    return Recorder()


@pytest.fixture
def dmx():
    return Recorder()


@pytest.fixture
def switch(midi, dmx):
    return OutputSwitch({'MIDI': midi, 'DMX': dmx}, 'MIDI')


def test_notes_go_only_to_the_active_output(switch, midi, dmx):
    switch.press_note(60)
    assert midi.notes == [60] and dmx.notes == []
    assert switch.active == 'MIDI' and switch.current is midi


def test_select_reroutes_later_notes(switch, midi, dmx):
    switch.select('DMX')
    switch.press_note(61)
    switch.select('MIDI')
    switch.press_note(62)
    assert midi.notes == [62] and dmx.notes == [61]


def test_unknown_name_is_rejected_and_keeps_the_current_output(switch, midi):
    with pytest.raises(KeyError, match='DMX2'):
        switch.select('DMX2')
    switch.press_note(63)
    assert switch.active == 'MIDI' and midi.notes == [63]


def test_initial_output_must_exist(midi):
    with pytest.raises(KeyError):
        OutputSwitch({'MIDI': midi}, 'DMX')


def test_needs_an_output():
    with pytest.raises(ValueError):
        OutputSwitch({}, 'MIDI')


def test_names_in_given_order(switch):
    assert switch.names == ['MIDI', 'DMX']


def test_later_changes_to_the_given_dict_dont_leak_in(midi, dmx):
    outputs = {'MIDI': midi}
    switch = OutputSwitch(outputs, 'MIDI')
    outputs['DMX'] = dmx
    with pytest.raises(KeyError):
        switch.select('DMX')
