"""The DMX (ART-NET) settings section on its own: node IP, universe and the
channel tester button."""

import pytest

from pylzr.gui import DMXSettings


@pytest.fixture
def dmx(qapp):
    return DMXSettings()


def capture(signal):
    received = []
    signal.connect(lambda *args: received.append(args[0] if len(args) == 1 else args))
    return received


def test_node_defaults(dmx):
    assert dmx._node_ip_edit.text() == '10.201.6.100'
    assert [s.value() for s in dmx._port_spins] == [0, 0, 0]
    assert [(s.minimum(), s.maximum()) for s in dmx._port_spins] == [(0, 127), (0, 15), (0, 15)]


def edit_ip(dmx, text):
    """Type into the IP field and press Enter, as a user would."""
    edit = dmx._node_ip_edit
    edit.setText(text)
    edit.editingFinished.emit()


def test_valid_ip_is_emitted_once(dmx):
    received = capture(dmx.node_changed)
    edit_ip(dmx, '192.168.1.250')
    edit_ip(dmx, '192.168.1.250')              # unchanged: no second emit
    assert received == [('192.168.1.250', [0, 0, 0])]


@pytest.mark.parametrize('typed', ['10.201.6', '10.201.6.', '300.1.1.1', ''])
def test_invalid_ip_reverts_to_the_last_good_one(dmx, typed):
    received = capture(dmx.node_changed)
    edit_ip(dmx, typed)
    assert dmx._node_ip_edit.text() == '10.201.6.100'
    assert received == []


def test_ip_field_only_accepts_ip_like_typing(dmx):
    from PyQt5.QtGui import QValidator
    validator = dmx._node_ip_edit.validator()
    assert validator.validate('10.20', 0)[0] == QValidator.Acceptable     # partial is fine while typing
    assert validator.validate('10.2x', 0)[0] == QValidator.Invalid
    assert validator.validate('1.2.3.4.5', 0)[0] == QValidator.Invalid


def test_universe_spins_emit_full_node(dmx):
    received = capture(dmx.node_changed)
    dmx._port_spins[2].setValue(3)
    dmx._port_spins[0].setValue(1)
    assert received == [('10.201.6.100', [0, 0, 3]), ('10.201.6.100', [1, 0, 3])]


def test_spin_change_while_ip_half_typed_keeps_last_good_ip(dmx):
    received = capture(dmx.node_changed)
    dmx._node_ip_edit.setText('10.2')          # not finished yet
    dmx._port_spins[1].setValue(2)
    assert received == [('10.201.6.100', [0, 2, 0])]


def test_set_node_emits_once_for_all_fields(dmx):
    received = capture(dmx.node_changed)
    dmx.set_node('10.201.6.101', [1, 2, 3])
    assert received == [('10.201.6.101', [1, 2, 3])]
    dmx.set_node('10.201.6.101', [1, 2, 3])
    assert len(received) == 1                    # same values: nothing to restore


def test_set_node_ignores_an_invalid_ip(dmx):
    received = capture(dmx.node_changed)
    dmx.set_node('not an ip', [0, 0, 1])
    assert dmx._node_ip_edit.text() == '10.201.6.100'
    assert received == [('10.201.6.100', [0, 0, 1])]


def test_tester_button(dmx):
    received = capture(dmx.tester_requested)
    assert not dmx._tester_btn.isEnabled()     # MIDI mode at start
    assert 'Control Mode to DMX' in dmx._tester_btn.toolTip()
    dmx.set_tester_enabled(True)
    dmx._tester_btn.click()
    assert len(received) == 1
    assert 'live' in dmx._tester_btn.toolTip()
