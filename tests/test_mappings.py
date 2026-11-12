"""Mapping types (pylzr.fixtures.mappings), with the Gruolin's ranges as
examples. Sweeps check every type over its whole input range: values stay
in range, move one way, and outputs() lists exactly what render() can send."""

import pytest

from pylzr.fixtures import Kind
from pylzr.fixtures.mappings import Bipolar, Direction, Linear, Options, Selected, dmx_round

STEPS = 4000


def unit_sweep():
    return [i / STEPS for i in range(STEPS + 1)]                 # 0 … 1


def bipolar_sweep():
    return [i / STEPS for i in range(-STEPS, STEPS + 1)]         # -1 … 1


def sent(mapping, attribute, inputs, **fixed):
    """{channel: set of values} rendered over `inputs` for `attribute`."""
    found: dict[str, set[int]] = {}
    for value in inputs:
        values = {**fixed, attribute: value}
        if mapping.active(values):
            for ch, dmx in mapping.render(values).items():
                found.setdefault(ch, set()).add(dmx)
    return found


def render_one(mapping, **values):
    [(_, dmx)] = mapping.render(values).items()
    return dmx


def test_rounding_is_half_up_everywhere():
    assert [dmx_round(v) for v in (0.5, 1.5, 2.5, 127.5, 2.49, 0.0)] == [1, 2, 3, 128, 2, 0]


# ── Linear ───────────────────────────────────────────────────────────────

def test_linear_runs_start_to_end():
    scan = Linear('scan_speed', 'Scan Speed', 64, 127)
    assert [render_one(scan, scan_speed=v) for v in (0, 0.5, 1)] == [64, 96, 127]   # 95.5 rounds up


def test_linear_can_run_downwards():
    """Gruolin pattern size runs large → small, so size 1 (largest) is DMX 0."""
    size = Linear('size', 'Pattern Size', 255, 0)
    assert [render_one(size, size=v) for v in (0, 0.5, 1)] == [255, 128, 0]


def test_linear_calibration_uses_part_of_the_range():
    size = Linear('size', 'Pattern Size', 255, 0, min=0.2, max=0.8)
    assert [render_one(size, size=v) for v in (0, 1)] == [204, 51]
    assert size.outputs() == {'Pattern Size': frozenset(range(51, 205))}


def test_linear_zero_value():
    """Strobe 0 sends 0 (off), anything above runs through 1–255."""
    strobe = Linear('strobe', 'Strobe', 1, 255, zero=0)
    assert [render_one(strobe, strobe=v) for v in (0, 0.0001, 1)] == [0, 1, 255]
    assert strobe.outputs() == {'Strobe': frozenset(range(256))}


def test_linear_can_release_its_channel_at_zero():
    """Gruolin ch19: wave_x at 0 lets wave_y have the Wave channel."""
    wave_x = Linear('wave_x', 'Wave', 1, 127, release_at_zero=True)
    assert not wave_x.active({'wave_x': 0.0}) and not wave_x.active({})
    assert wave_x.active({'wave_x': 0.0001})
    assert [render_one(wave_x, wave_x=v) for v in (0.0001, 1)] == [1, 127]
    assert wave_x.outputs() == {'Wave': frozenset(range(1, 128))}
    assert wave_x.off_values() == {}


def test_linear_off_value_is_its_zero():
    assert Linear('strobe', 'Strobe', 1, 255, zero=0).off_values() == {'Strobe': frozenset({0})}
    assert Linear('size', 'Pattern Size', 255, 0).off_values() == {}


@pytest.mark.parametrize('mapping', [
    Linear('size', 'Pattern Size', 255, 0),
    Linear('size', 'Pattern Size', 255, 0, min=0.1, max=0.9),
    Linear('scan_speed', 'Scan Speed', 128, 255),
    Linear('strobe', 'Strobe', 1, 255, zero=0),
    Linear('zoom', 'Zoom', 0, 127, min=0.5, max=0.5),
    Linear('wave_y', 'Wave', 128, 255, release_at_zero=True),
])
def test_linear_sweep(mapping):
    found = sent(mapping, mapping.attribute, unit_sweep())
    assert found == {k: set(v) for k, v in mapping.outputs().items()}
    values = [render_one(mapping, **{mapping.attribute: v}) for v in unit_sweep()[1:]]
    assert values == sorted(values, reverse=mapping.start > mapping.end)       # one way only


def test_linear_is_inactive_without_its_attribute():
    size = Linear('size', 'Pattern Size', 255, 0)
    assert not size.active({}) and not size.active({'zoom': 1.0})
    assert size.active({'size': 0.0})
    assert (size.kinds, size.attributes, size.channels) == ({'size': Kind.CONTINUOUS}, ('size',), ('Pattern Size',))


@pytest.mark.parametrize('kwargs, message', [
    (dict(start=-1, end=10), 'start must be a DMX value'),
    (dict(start=0, end=256), 'end must be a DMX value'),
    (dict(start=0, end=True), 'end must be a DMX value'),
    (dict(start=0, end=255, min=0.6, max=0.4), r'min \(0.6\) is above max \(0.4\)'),
    (dict(start=0, end=255, max=1.5), 'max must be a number from 0 to 1'),
    (dict(start=0, end=255, zero=300), 'zero must be a DMX value'),
    (dict(start=1, end=255, zero=0, release_at_zero=True), 'either sends zero or releases the channel'),
])
def test_bad_linear(kwargs, message):
    with pytest.raises(ValueError, match=message):
        Linear('size', 'Pattern Size', **kwargs)


# ── Bipolar ──────────────────────────────────────────────────────────────

def test_bipolar_centre_and_ends():
    """Gruolin position: 0 … 128 (centre) … 255; each half scaled on its own."""
    pos = Bipolar('pos_x', 'Horizontal Position', 0, 128, 255)
    assert [render_one(pos, pos_x=v) for v in (-1, -0.5, 0, 0.5, 1)] == [0, 64, 128, 192, 255]   # 191.5 → 192


def test_bipolar_limit_keeps_it_near_the_centre():
    pos = Bipolar('pos_x', 'Horizontal Position', 0, 128, 255, limit=0.5)
    assert [render_one(pos, pos_x=v) for v in (-1, 0, 1)] == [64, 128, 192]
    assert pos.outputs() == {'Horizontal Position': frozenset(range(64, 193))}


def test_bipolar_can_be_inverted_by_swapping_ends():
    pos = Bipolar('pos_y', 'Vertical Position', 255, 128, 0)
    assert [render_one(pos, pos_y=v) for v in (-1, 0, 1)] == [255, 128, 0]


@pytest.mark.parametrize('mapping', [
    Bipolar('pos_x', 'Horizontal Position', 0, 128, 255),
    Bipolar('pos_x', 'Horizontal Position', 0, 128, 255, limit=0.6),
    Bipolar('pos_y', 'Vertical Position', 255, 128, 0, limit=0.3),
    Bipolar('x_shift', 'Horizontal Movement', 1, 64, 127),
])
def test_bipolar_sweep(mapping):
    found = sent(mapping, mapping.attribute, bipolar_sweep())
    assert found == {k: set(v) for k, v in mapping.outputs().items()}
    values = [render_one(mapping, **{mapping.attribute: v}) for v in bipolar_sweep()]
    assert values == sorted(values, reverse=mapping.low > mapping.high)


@pytest.mark.parametrize('args, kwargs, message', [
    ((0, 300, 255), {}, 'centre must be a DMX value'),
    ((0, 20, 10), {}, r'centre \(20\) must lie between low \(0\) and high \(10\)'),
    ((0, 128, 255), {'limit': 0}, 'limit must be above 0'),
    ((0, 128, 255), {'limit': 1.2}, 'limit must be above 0'),
])
def test_bad_bipolar(args, kwargs, message):
    with pytest.raises(ValueError, match=message):
        Bipolar('pos_x', 'Horizontal Position', *args, **kwargs)


# ── Direction ────────────────────────────────────────────────────────────

def spin():
    """Gruolin Rotation Z: 128–191 clockwise slow → fast, 192–255 anticlockwise."""
    return Direction('spin_z', 'Rotation Z', forward=(128, 191), reverse=(192, 255))


def test_direction_forward_and_reverse_get_faster():
    assert [render_one(spin(), spin_z=v) for v in (0.01, 0.5, 1)] == [129, 160, 191]     # 159.5 → 160
    assert [render_one(spin(), spin_z=v) for v in (-0.01, -0.5, -1)] == [193, 224, 255]


def test_direction_without_off_hands_the_channel_back_at_zero():
    assert not spin().active({'spin_z': 0.0})
    assert spin().active({'spin_z': 0.2}) and not spin().active({})


def test_direction_with_off_sends_it_at_zero():
    """Gruolin colour speed: 0–3 still, 4–127 forwards, 128–255 backwards."""
    speed = Direction('color_speed', 'Color Speed', forward=(4, 127), reverse=(128, 255), off=0)
    assert speed.active({'color_speed': 0.0})
    assert [render_one(speed, color_speed=v) for v in (0, 1, -1)] == [0, 127, 255]
    assert speed.off_values() == {'Color Speed': frozenset({0})}
    assert spin().off_values() == {}


def test_direction_deadband():
    speed = Direction('move_x', 'Horizontal Movement', forward=(128, 159), reverse=(160, 191), off=0, deadband=0.1)
    assert [render_one(speed, move_x=v) for v in (0.05, -0.1, 0.1001, 1)] == [0, 0, 128, 159]


def test_direction_segments_may_run_fast_to_slow():
    """Some profiles give speeds fast → slow in DMX order (the EL-400 does)."""
    speed = Direction('move_x', 'Speed', forward=(127, 0), reverse=(128, 255))
    assert [render_one(speed, move_x=v) for v in (0.001, 1)] == [127, 0]


@pytest.mark.parametrize('mapping', [
    spin(),
    Direction('color_speed', 'Color Speed', forward=(4, 127), reverse=(128, 255), off=0),
    Direction('move_x', 'Movement', forward=(128, 159), reverse=(160, 191), deadband=0.25),
    Direction('move_x', 'Speed', forward=(127, 0), reverse=(128, 255), off=0),
])
def test_direction_sweep(mapping):
    found = sent(mapping, mapping.attribute, bipolar_sweep())
    assert found == {k: set(v) for k, v in mapping.outputs().items()}


@pytest.mark.parametrize('kwargs, message', [
    (dict(forward=(128,), reverse=(192, 255)), r'forward must be \(slow, fast\)'),
    (dict(forward=(128, 300), reverse=(192, 255)), 'forward must be a DMX value'),
    (dict(forward=(128, 191), reverse=(192, 255), off=-1), 'off must be a DMX value'),
    (dict(forward=(128, 191), reverse=(192, 255), deadband=1), 'deadband must be a number from 0 to 0.99'),
])
def test_bad_direction(kwargs, message):
    with pytest.raises(ValueError, match=message):
        Direction('spin_z', 'Rotation Z', **kwargs)


# ── Options ──────────────────────────────────────────────────────────────

def colours():
    return Options('color', {'white': {'Color': 0}, 'red': {'Color': 8}, 'magenta': {'Color': 28}})


def test_options_send_fixed_values():
    assert colours().render({'color': 'red'}) == {'Color': 8}
    assert colours().kinds == {'color': Kind.OPTION}


def test_choices_the_fixture_lacks_are_ignored():
    assert not colours().active({'color': 'cyan'})
    assert not colours().active({})


def test_one_choice_can_set_several_channels():
    """E.g. a pattern needs its group *and* its number."""
    patterns = Options('x_pattern_raw', {
        'tunnel': {'Pattern Group': 64, 'Pattern Selection': 15},
        'line': {'Pattern Group': 1, 'Pattern Selection': 5},
        'off': {'Pattern Selection': 0},
    })
    assert patterns.render({'x_pattern_raw': 'tunnel'}) == {'Pattern Group': 64, 'Pattern Selection': 15}
    assert patterns.channels == ('Pattern Group', 'Pattern Selection')
    assert patterns.outputs() == {'Pattern Group': frozenset({64, 1}), 'Pattern Selection': frozenset({15, 5, 0})}


def test_options_off_values_and_choices():
    """Only choices called off or none may mean "nothing"."""
    power = Options('power', {'off': {'On/Off': 0}, 'on': {'On/Off': 255}})
    assert power.off_values() == {'On/Off': frozenset({0})}
    assert power.options() == {'power': frozenset({'off', 'on'})}
    effect = Options('color_effect', {'none': {'Color': 0}, 'jump': {'Color': 32}, 'gradient': {'Color': 240}})
    assert effect.off_values() == {'Color': frozenset({0})}
    assert colours().off_values() == {}


def test_option_values_are_read_only():
    with pytest.raises(TypeError):
        colours().values['red']['Color'] = 9                                   # type: ignore[index]


@pytest.mark.parametrize('values, message', [
    ({}, 'needs at least one choice'),
    ({'red': {}}, 'choice "red" sets no channel'),
    ({'Red': {'Color': 8}}, 'choice "Red" is not an attribute name'),
    ({'red': {'Color': 256}}, 'red on "Color" must be a DMX value'),
])
def test_bad_options(values, message):
    with pytest.raises(ValueError, match=message):
        Options('color', values)


# ── Selected ─────────────────────────────────────────────────────────────

def scan():
    """Gruolin ch10: draw style picks the segment, scan speed the value in it."""
    return Selected('draw_style', {
        'line': Linear('scan_speed', 'Scan Speed', 64, 127),
        'dots': Linear('scan_speed', 'Scan Speed', 128, 255),
    }, default='line')


def test_selector_picks_the_segment():
    assert scan().render({'draw_style': 'dots', 'scan_speed': 1.0}) == {'Scan Speed': 255}
    assert scan().render({'draw_style': 'line', 'scan_speed': 1.0}) == {'Scan Speed': 127}


def test_unset_selector_uses_the_default():
    assert scan().render({'scan_speed': 0.0}) == {'Scan Speed': 64}


def test_selector_alone_or_an_unknown_choice_does_nothing():
    assert not scan().active({'draw_style': 'dots'})                       # no speed to send
    assert not scan().active({'draw_style': 'zigzag', 'scan_speed': 0.5})


def test_selected_directions():
    """Gruolin movement styles: wrap and gap each have a forward/reverse pair."""
    movement = Selected('x_move_style', {
        'wrap': Direction('move_x', 'Horizontal Movement', forward=(128, 159), reverse=(160, 191)),
        'gap': Direction('move_x', 'Horizontal Movement', forward=(192, 223), reverse=(224, 255)),
    }, default='wrap')
    assert movement.render({'move_x': 1.0}) == {'Horizontal Movement': 159}
    assert movement.render({'move_x': -1.0, 'x_move_style': 'gap'}) == {'Horizontal Movement': 255}
    assert not movement.active({'move_x': 0.0})                            # hands the channel back
    assert movement.kinds == {'x_move_style': Kind.OPTION, 'move_x': Kind.BIPOLAR}
    assert movement.outputs() == {'Horizontal Movement': frozenset(range(128, 256))}


def test_selected_sweep():
    mapping = scan()
    for style in ('line', 'dots'):
        found = sent(mapping, 'scan_speed', unit_sweep(), draw_style=style)
        assert found == {k: set(v) for k, v in mapping.choices[style].outputs().items()}
    assert mapping.outputs() == {'Scan Speed': frozenset(range(64, 256))}
    assert mapping.attributes == ('draw_style', 'scan_speed') and mapping.channels == ('Scan Speed',)


def test_selected_off_values_and_choices_come_from_every_choice():
    zoom = Selected('zoom_style', {
        'shrink': Linear('zoom_motion', 'Zoom', 128, 159, release_at_zero=True),
        'pulse': Direction('x_pulse', 'Zoom', forward=(192, 223), reverse=(224, 255), off=0),
        'grow': Selected('x_variant', {'one': Linear('zoom_motion', 'Zoom', 160, 191, zero=5)}, 'one'),
    }, default='shrink')
    assert zoom.off_values() == {'Zoom': frozenset({0, 5})}
    assert zoom.options() == {'zoom_style': frozenset({'shrink', 'pulse', 'grow'}), 'x_variant': frozenset({'one'})}


def test_gradient_mappings_read_no_options():
    assert Linear('size', 'Pattern Size', 255, 0).options() == {}
    assert Bipolar('pos_x', 'Horizontal Position', 0, 128, 255).options() == {}
    assert Bipolar('pos_x', 'Horizontal Position', 0, 128, 255).off_values() == {}


@pytest.mark.parametrize('choices, default, message', [
    ({}, 'line', 'needs at least one choice'),
    ({'line': Linear('scan_speed', 'Scan Speed', 64, 127)}, 'dots', 'default "dots" is not one of the choices'),
    ({'line': Linear('draw_style', 'Scan Speed', 64, 127)}, 'line', 'reads its own selector'),
    ({'line': 'not a mapping'}, 'line', 'must be a mapping'),
])
def test_bad_selected(choices, default, message):
    with pytest.raises(ValueError, match=message):
        Selected('draw_style', choices, default)


@pytest.mark.parametrize('make', [
    lambda: Linear('Size', 'Pattern Size', 0, 255),
    lambda: Bipolar('pos x', 'Horizontal Position', 0, 128, 255),
    lambda: Direction('', 'Rotation Z', (128, 191), (192, 255)),
    lambda: Options('Color', {'red': {'Color': 8}}),
    lambda: Selected('Draw', {'line': Linear('scan_speed', 'Scan Speed', 64, 127)}, 'line'),
])
def test_attribute_names_are_checked(make):
    with pytest.raises(ValueError, match='is not an attribute name'):
        make()
