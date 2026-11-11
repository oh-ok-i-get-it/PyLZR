"""The shipped Gruolin binding (36-channel mode): loads as a package resource,
resolves against the shipped profile, saves back to the same bytes, covers
the shared attributes, and sends what was checked on the laser."""

from importlib.resources import as_file, files

import pytest

from pylzr.fixtures import CORE, PatternMapping, PatternRequest, read_binding, read_profile
from pylzr.fixtures.jsonio import dumps

KEY = 'gruolin/rgb-beam-36ch'


def resource(*parts):
    return files('pylzr.fixtures').joinpath('data', *parts)


@pytest.fixture(scope='module')
def binding():
    with as_file(resource('bindings', f'{KEY}.json')) as path:
        return read_binding(path, KEY)


@pytest.fixture(scope='module')
def gruolin(binding):
    with as_file(resource('profiles', f'{binding.profile}.json')) as path:
        return binding.resolve(read_profile(path, binding.profile))


def first(resolved, attribute):
    """The highest-priority mapping reading `attribute`."""
    return next(m for m in resolved.mappings if attribute in m.attributes)


def position(resolved, attribute):
    return next(i for i, m in enumerate(resolved.mappings) if attribute in m.attributes)


def send(resolved, attribute, value, **others):
    mapping = first(resolved, attribute)
    values = {attribute: value, **others}
    return mapping.render(values) if mapping.active(values) else None


# ── The file ─────────────────────────────────────────────────────────────

def test_identity(binding, gruolin):
    assert (binding.key, binding.name, binding.mode) == (KEY, 'Gruolin RGB Beam (36ch)', '36ch')
    assert binding.profile == 'gruolin/rgb-fullcolor-beam-effect-light'
    assert gruolin.mode.footprint == 36 and gruolin.layers == ('a', 'b')


def test_the_file_is_in_canonical_form(binding):
    """Saving it changes nothing, so tagging patterns later gives a clean diff."""
    assert resource('bindings', f'{KEY}.json').read_bytes() == dumps(binding.to_json()).encode('utf-8')


def test_every_shared_attribute_is_mapped_except_events(gruolin):
    mapped = {name for m in gruolin.mappings for name in m.attributes}
    assert {name for name, a in CORE.items() if a.kind != 'event'} <= mapped
    assert 'blackout' not in mapped                                       # events come with scenes (D3)


def test_gruolin_only_features_are_extras(gruolin):
    extras = {a.name for a in gruolin.attributes if a.is_extra}
    assert extras == {'x_flowing_water', 'x_color_change', 'x_bright_scan', 'x_move_style', 'x_shift_x',
                      'x_shift_y', 'x_zoom_pulse_2'}
    assert gruolin.attributes['x_flowing_water'].options == tuple(f'water_{n}' for n in range(1, 50))


def test_layer_b_is_the_second_pattern(gruolin):
    assert gruolin.channel('Pattern Size', 'b') == 'Pattern Size 2'
    assert gruolin.channel('Pattern Selection', 'b') == 'Pattern Selection 2'
    power = gruolin.mappings.index(first(gruolin, 'power'))
    assert gruolin.layered[power] is False                               # On/Off is never shifted


# ── What it sends (checked on the laser, Nov 2026) ───────────────────────

def test_power(gruolin):
    assert send(gruolin, 'power', 'on') == {'On/Off': 255} and send(gruolin, 'power', 'off') == {'On/Off': 0}


def test_no_pattern_means_number_zero(gruolin):
    patterns = gruolin.mappings[0]
    assert isinstance(patterns, PatternMapping) and patterns.library.entries == ()       # you tag them
    assert patterns.channels == ('Pattern Group', 'Pattern Selection')
    assert patterns.render({}) == patterns.render({'pattern': PatternRequest.of('tunnel')}) == {
        'Pattern Selection': 0}


@pytest.mark.parametrize('attribute, value, sent', [
    ('size', 1.0, 0), ('size', 0.0, 255),                                     # the channel runs large → small
    ('pos_x', 0.0, 128), ('pos_x', -1.0, 64), ('pos_x', 1.0, 192),            # centre 128, half on-screen at the ends
    ('pos_y', 1.0, 192),
    ('strobe', 0.0, 0), ('strobe', 1.0, 255),
    ('rot_z', 0.0, 0), ('rot_z', 1.0, 127),
    ('spin_z', 1.0, 191), ('spin_z', -1.0, 255), ('spin_z', 0.01, 129),       # clockwise 128–191, anticlockwise 192–255
    ('spin_x', 1.0, 191), ('spin_y', -1.0, 255),
    ('color_speed', 0.0, 0), ('color_speed', 1.0, 127), ('color_speed', -1.0, 255),
    ('move_x', 1.0, 159), ('move_x', -1.0, 191),
    ('x_shift_x', 0.0, 64), ('x_shift_x', -1.0, 1), ('x_shift_x', 1.0, 127),
    ('zoom', 1.0, 0), ('zoom', 0.0, 127),                                     # full size … a dot
    ('zoom_motion', 1.0, 159),                                                # shrink by default
    ('gradient_speed', 0.0, 0), ('gradient_speed', 1.0, 255),
    ('wave_x', 1.0, 127), ('wave_y', 1.0, 255),
    ('x_bright_scan', 1.0, 63), ('x_zoom_pulse_2', 1.0, 255),
])
def test_values(gruolin, attribute, value, sent):
    [(channel, dmx)] = send(gruolin, attribute, value).items()
    assert dmx == sent


@pytest.mark.parametrize('color, sent', [('white', 4), ('red', 8), ('yellow', 12), ('green', 16), ('cyan', 20),
                                         ('blue', 24), ('magenta', 28), ('original', 1)])
def test_colours(gruolin, color, sent):
    assert send(gruolin, 'color', color) == {'Color': sent}


def test_colour_effects(gruolin):
    assert send(gruolin, 'color_effect', 'jump') == {'Color': 32}
    assert send(gruolin, 'color_effect', 'gradient') == {'Color': 240}
    assert send(gruolin, 'color_effect', 'none') is None                  # leaves the channel to color
    assert send(gruolin, 'color_effect', 'fade') is None                  # not on this laser
    assert send(gruolin, 'x_color_change', 'rgb') == {'Color': 36}
    assert send(gruolin, 'x_flowing_water', 'water_1') == {'Color': 44}
    assert send(gruolin, 'x_flowing_water', 'water_49') == {'Color': 236}


def test_selected_segments(gruolin):
    assert send(gruolin, 'scan_speed', 1.0) == {'Scan Speed': 127}                      # line by default
    assert send(gruolin, 'scan_speed', 1.0, draw_style='dots') == {'Scan Speed': 255}
    assert send(gruolin, 'move_x', 1.0, x_move_style='gap') == {'Horizontal Movement': 223}
    assert send(gruolin, 'move_y', -1.0, x_move_style='gap') == {'Vertical Movement': 255}
    assert send(gruolin, 'zoom_motion', 1.0, zoom_style='grow') == {'Zoom': 191}
    assert send(gruolin, 'zoom_motion', 1.0, zoom_style='pulse') == {'Zoom': 223}


@pytest.mark.parametrize('motion, static', [
    ('spin_z', 'rot_z'), ('spin_x', 'rot_x'), ('spin_y', 'rot_y'), ('move_x', 'x_shift_x'), ('move_y', 'x_shift_y'),
    ('zoom_motion', 'zoom'), ('x_zoom_pulse_2', 'zoom_motion'), ('wave_x', 'wave_y'), ('x_bright_scan', 'scan_speed'),
])
def test_a_motion_at_zero_hands_its_channel_on(gruolin, motion, static):
    """Shared channels: the motion comes first and lets go at 0."""
    assert position(gruolin, motion) < position(gruolin, static)
    assert send(gruolin, motion, 0.0) is None


@pytest.mark.parametrize('special, general', [
    ('x_flowing_water', 'color'), ('x_color_change', 'color'), ('color_effect', 'color'),
])
def test_colour_effects_come_before_fixed_colours(gruolin, special, general):
    assert position(gruolin, special) < position(gruolin, general)
