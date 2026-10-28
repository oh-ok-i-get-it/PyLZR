import pytest

from pylzr.dmx import DMXUniverse


@pytest.fixture
def uni():
    return DMXUniverse()


def test_starts_dark(uni):
    assert uni.frame() == bytes(512)
    assert not uni.has_overrides


def test_channels_are_numbered_from_1(uni):
    uni.set(1, 11)
    uni.set(512, 99)
    frame = uni.frame()
    assert len(frame) == 512
    assert frame[0] == 11 and frame[511] == 99
    assert uni.get(1) == 11 and uni.get(512) == 99


def test_set_range(uni):
    uni.set_range(10, [1, 2, 3])
    assert uni.frame()[8:13] == bytes([0, 1, 2, 3, 0])
    uni.set_range(510, [7, 8, 9])                # ends exactly on channel 512
    assert uni.frame()[-3:] == bytes([7, 8, 9])


@pytest.mark.parametrize('start, values', [
    (0, [1]), (513, [1]), (511, [1, 2, 3]), (-1, [1]), (1.0, [1]),
])
def test_channels_outside_1_to_512_are_rejected(uni, start, values):
    with pytest.raises(ValueError):
        uni.set_range(start, values)
    with pytest.raises(ValueError):
        uni.set_overrides(start, values)
    assert uni.frame() == bytes(512)             # nothing partly applied


@pytest.mark.parametrize('value', [-1, 256])
def test_values_outside_0_to_255_are_rejected(uni, value):
    with pytest.raises(ValueError):
        uni.set(1, value)
    with pytest.raises(ValueError):
        uni.set_overrides(1, [value])


def test_a_bare_int_is_not_taken_as_a_count(uni):
    with pytest.raises(TypeError):
        uni.set_range(1, 5)                      # would otherwise zero 5 channels


def test_get_rejects_bad_channel(uni):
    with pytest.raises(ValueError):
        uni.get(0)


def test_overrides_win_without_changing_the_base(uni):
    uni.set_range(1, [10, 20, 30])
    uni.set_overrides(2, [200, 0])
    assert uni.frame()[:4] == bytes([10, 200, 0, 0])   # an override of 0 also wins
    assert uni.get(2) == 20 and uni.has_overrides
    uni.clear_overrides()
    assert uni.frame()[:4] == bytes([10, 20, 30, 0])
    assert not uni.has_overrides


def test_new_overrides_replace_old_ones(uni):
    """The tester moving its start address releases the channels it left."""
    uni.set_range(1, [5, 5, 5, 5])
    uni.set_overrides(1, [100, 100])
    uni.set_overrides(3, [100, 100])
    assert uni.frame()[:4] == bytes([5, 5, 100, 100])


def test_base_changes_under_overrides_show_once_cleared(uni):
    uni.set_overrides(1, [255])
    uni.set(1, 42)
    assert uni.frame()[0] == 255
    uni.clear_overrides()
    assert uni.frame()[0] == 42


def test_clear_resets_base_but_keeps_overrides(uni):
    uni.set_range(1, [9, 9])
    uni.set_overrides(2, [77])
    uni.clear()
    assert uni.frame()[:2] == bytes([0, 77])
