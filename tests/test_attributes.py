"""The attribute vocabulary (pylzr.fixtures.attributes)."""

import math

import pytest

from pylzr.fixtures import (
    CORE, CORE_ATTRIBUTES, AttrKey, Attribute, AttributeSet, Kind, PatternRequest, make_extra,
)
from pylzr.fixtures.attributes import COLORS

# ── The core list ────────────────────────────────────────────────────────

def test_core_list_as_agreed():
    """What any laser could do, in display order. Features only one laser has
    are extras in its binding, never core attributes."""
    assert [a.name for a in CORE_ATTRIBUTES] == [
        'power', 'pattern', 'size', 'pos_x', 'pos_y', 'color', 'color_effect', 'color_speed',
        'draw_style', 'scan_speed', 'strobe', 'rot_x', 'rot_y', 'rot_z', 'spin_x', 'spin_y', 'spin_z',
        'move_x', 'move_y', 'zoom', 'zoom_motion', 'zoom_style', 'gradient_speed', 'wave_x', 'wave_y',
        'blackout']
    assert list(CORE) == [a.name for a in CORE_ATTRIBUTES]


def test_core_kinds_and_options():
    kinds = {a.name: a.kind for a in CORE_ATTRIBUTES}
    assert [n for n, k in kinds.items() if k == Kind.BIPOLAR] == [
        'pos_x', 'pos_y', 'color_speed', 'spin_x', 'spin_y', 'spin_z', 'move_x', 'move_y']
    assert [n for n, k in kinds.items() if k == Kind.OPTION] == [
        'power', 'color', 'color_effect', 'draw_style', 'zoom_style']
    assert kinds['pattern'] == Kind.PATTERN and kinds['blackout'] == Kind.EVENT
    assert CORE['color'].options == COLORS == (
        'white', 'red', 'yellow', 'green', 'cyan', 'blue', 'magenta', 'original')
    assert CORE['power'].options == ('off', 'on')
    assert CORE['color_effect'].options == ('none', 'jump', 'fade', 'gradient')
    assert CORE['draw_style'].options == ('line', 'dots')
    assert CORE['zoom_style'].options == ('shrink', 'grow', 'pulse')


def test_only_power_and_blackout_belong_to_the_whole_fixture():
    assert [a.name for a in CORE_ATTRIBUTES if not a.layered] == ['power', 'blackout']


def test_core_list_is_read_only():
    with pytest.raises(TypeError):
        CORE['size'] = None                          # type: ignore[index]
    assert all(a.description for a in CORE_ATTRIBUTES)
    assert not any(a.is_extra for a in CORE_ATTRIBUTES)


# ── Values ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize('name, value, expected', [
    ('size', 0, 0.0), ('size', 1, 1.0), ('size', 0.25, 0.25),
    ('pos_x', -1, -1.0), ('pos_x', 0.5, 0.5), ('spin_z', 1, 1.0),
    ('color', 'magenta', 'magenta'), ('power', 'on', 'on'),
    ('blackout', True, True),
])
def test_valid_values(name, value, expected):
    result = CORE[name].validate(value)
    assert result == expected and type(result) is type(expected)


@pytest.mark.parametrize('name, value, message', [
    ('size', -0.01, 'size must be a number from 0 to 1'),
    ('size', 1.5, 'size must be a number from 0 to 1'),
    ('size', True, 'size must be a number from 0 to 1'),
    ('size', '0.5', 'size must be a number from 0 to 1'),
    ('size', math.nan, 'size must be a number from 0 to 1'),
    ('pos_x', -1.01, 'pos_x must be a number from -1 to 1'),
    ('color', 'purple', 'color must be one of white, red'),
    ('pattern', 'tunnel', 'pattern must be a PatternRequest'),
    ('blackout', 1, 'blackout is an event'),
])
def test_invalid_values(name, value, message):
    with pytest.raises(ValueError, match=message):
        CORE[name].validate(value)


def test_pattern_value():
    request = PatternRequest.of('tunnel', energy=0.8)
    assert CORE['pattern'].validate(request) is request


# ── Defining attributes ──────────────────────────────────────────────────

@pytest.mark.parametrize('kwargs, message', [
    (dict(name='Size', kind='continuous'), 'not an attribute name'),
    (dict(name='2d', kind='continuous'), 'not an attribute name'),
    (dict(name='mode', kind='option'), 'needs its options'),
    (dict(name='mode', kind='option', options=('a', 'a')), 'lists an option twice'),
    (dict(name='mode', kind='option', options=('Fast',)), 'not an option name'),
    (dict(name='size', kind='continuous', options=('a',)), 'only option attributes have options'),
    (dict(name='size', kind='sideways'), 'not a valid Kind'),
])
def test_bad_attribute_definitions(kwargs, message):
    with pytest.raises(ValueError, match=message):
        Attribute(description='', **kwargs)


def test_extras_need_the_x_prefix():
    extra = make_extra('x_laser_wave', 'bipolar', 'Gruolin-only wave')
    assert extra.is_extra and extra.kind == Kind.BIPOLAR and extra.layered
    for name in ('laser_wave', 'x_'):
        with pytest.raises(ValueError, match='must be named x_<something>'):
            make_extra(name, 'continuous')
    with pytest.raises(ValueError, match='"wobble" is not a kind of attribute'):
        make_extra('x_wave', 'wobble')


# ── Keys ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('text, name, layer, canonical', [
    ('size', 'size', 'a', 'size'),
    ('size@a', 'size', 'a', 'size'),
    ('size@b', 'size', 'b', 'size@b'),
    ('x_flow@c', 'x_flow', 'c', 'x_flow@c'),
])
def test_keys_parse_and_print(text, name, layer, canonical):
    key = AttrKey.parse(text)
    assert (key.name, key.layer, str(key)) == (name, layer, canonical)
    assert AttrKey.parse(key) is key
    assert AttrKey.parse(str(key)) == key


@pytest.mark.parametrize('text', ['', '@b', 'size@', 'size@B', 'Size', 'size@b@c', 'size@ab', 'size b'])
def test_bad_keys(text):
    with pytest.raises(ValueError):
        AttrKey.parse(text)


def test_keys_sort_by_name_then_layer():
    keys = [AttrKey.parse(t) for t in ('size@b', 'pos_x', 'size')]
    assert [str(k) for k in sorted(keys)] == ['pos_x', 'size', 'size@b']


# ── Pattern requests ─────────────────────────────────────────────────────

def test_pattern_request_by_category_and_scales():
    request = PatternRequest.of('tunnel', sharpness=0.4, energy=0.8)
    assert request.category == 'tunnel'
    assert request.scales == (('energy', 0.8), ('sharpness', 0.4))      # sorted, so equal requests are equal
    assert request == PatternRequest.of('tunnel', energy=0.8, sharpness=0.4)
    assert request.scale_values == {'energy': 0.8, 'sharpness': 0.4}
    assert PatternRequest.of('tunnel', energy=1).scales == (('energy', 1.0),)


def test_pattern_request_by_entry_name():
    request = PatternRequest.entry('tunnel 3')
    assert (request.name, request.category, request.scales) == ('tunnel 3', '', ())


@pytest.mark.parametrize('kwargs, message', [
    ({}, 'needs a category or an entry name'),
    ({'category': 'tunnel', 'name': 'tunnel 3'}, 'needs a category or an entry name'),
    ({'name': 'tunnel 3', 'scales': (('energy', 0.5),)}, 'scales only go with a category'),
    ({'category': 'tunnel', 'scales': (('energy', 1.2),)}, 'scale "energy" must be a number from 0 to 1'),
    ({'category': 'tunnel', 'scales': (('Energy', 0.2),)}, 'is not a scale name'),
    ({'category': 'tunnel', 'scales': (('energy', 0.2), ('energy', 0.4))}, 'given twice'),
])
def test_bad_pattern_requests(kwargs, message):
    with pytest.raises(ValueError, match=message):
        PatternRequest(**kwargs)


# ── Attribute sets (core + a binding's extras) ───────────────────────────

def test_set_has_core_then_extras():
    extra = make_extra('x_flow', 'option', options=('one', 'two'))
    attributes = AttributeSet([extra])
    assert [a.name for a in attributes][-2:] == ['blackout', 'x_flow']
    assert 'x_flow' in attributes and 'size' in attributes and 'x_other' not in attributes
    assert attributes['x_flow'] is extra


def test_set_refuses_core_names_and_duplicates_as_extras():
    with pytest.raises(ValueError, match='must be named x_'):
        AttributeSet([Attribute('size', Kind.CONTINUOUS, '')])
    with pytest.raises(ValueError, match='defined twice'):
        AttributeSet([make_extra('x_a', 'continuous'), make_extra('x_a', 'bipolar')])


def test_unknown_attribute_has_a_hint():
    with pytest.raises(KeyError, match='unknown attribute "sise" \\(did you mean "size"\\?\\)'):
        AttributeSet()['sise']


def test_validate_state_normalises_keys_and_values():
    state = AttributeSet().validate_state({'size': 1, 'pos_x@b': -0.5, 'power': 'on'})
    assert state == {AttrKey('size'): 1.0, AttrKey('pos_x', 'b'): -0.5, AttrKey('power'): 'on'}
    assert all(isinstance(k, AttrKey) for k in state)


@pytest.mark.parametrize('state, message', [
    ({'size': 0.5, 'size@a': 0.6}, '"size" is given twice'),
    ({'power@b': 'on'}, 'power belongs to the whole fixture, so it has no layer'),
    ({'sise': 0.5}, 'unknown attribute "sise"'),
    ({'size': 2}, 'size must be a number from 0 to 1'),
    ({'size@B': 0.5}, 'not a layer'),
])
def test_bad_states(state, message):
    with pytest.raises(ValueError, match=message):
        AttributeSet().validate_state(state)
