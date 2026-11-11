"""The renderer (pylzr.fixtures.renderer): whole attribute states → exact
channel values, shared channels, layers, and what's reported as unsupported
or ignored. Mostly on the shipped Gruolin (36 channels; layer b is 17 on)."""

import pytest
from sample_fixture import KEY, profile
from shipped import channels, renderer

from pylzr.fixtures import AttrKey, PatternEntry, PatternRequest, Renderer, compile_fixture, load_binding

# Channels nothing drives: positions centred at 128 (profile defaults), the rest 0
DEFAULTS = {ch: 128 if ch in (6, 7, 23, 24) else 0 for ch in range(1, 37)}


def sent(state) -> dict[int, int]:
    """The channels that differ from the defaults, 1-based."""
    values = renderer().render(state).values
    assert len(values) == 36
    return {ch: v for ch, v in enumerate(values, start=1) if v != DEFAULTS[ch]}


# ── Defaults and identity ────────────────────────────────────────────────

def test_nothing_set_sends_the_defaults():
    r = renderer()
    assert list(r.defaults) == [DEFAULTS[ch] for ch in range(1, 37)]
    result = r.render({})
    assert result.values == r.defaults and result.unsupported == result.ignored == ()
    assert dict(result.patterns) == {'a': None, 'b': None}


def test_about_the_fixture():
    r = renderer()
    assert (r.key, r.name, r.footprint, r.layers) == ('gruolin/rgb-beam-36ch', 'Gruolin RGB Beam (36ch)', 36,
                                                      ('a', 'b'))
    assert r.supports('size@b') and r.supports(AttrKey('power')) and r.supports('x_shift_x')
    assert not r.supports('power@b') and not r.supports('size@c') and not r.supports('blackout')
    assert r.choices('color_effect') == {'jump', 'gradient'} and r.choices('size') == frozenset()


def test_rendering_is_stateless():
    r = renderer()
    first = r.render({'size': 0.3, 'color': 'red'})
    r.render({'size': 1.0, 'spin_z': 0.5})
    assert r.render({'size': 0.3, 'color': 'red'}) == first


# ── Exact values ─────────────────────────────────────────────────────────

def test_a_typical_look():
    state = {'power': 'on', 'size': 1.0, 'pos_x': -1.0, 'color': 'blue', 'spin_z': 0.5, 'strobe': 0.0}
    assert sent(state) == channels(ch1=255, ch6=64, ch8=24, ch12=160)       # size 1 is DMX 0, the default


def test_layer_b_lands_17_channels_on_and_power_is_never_shifted():
    assert sent({'size@b': 0.0, 'color@b': 'red', 'power': 'on'}) == channels(ch1=255, ch22=255, ch25=8)
    assert sent({'size': 0.0, 'size@b': 0.5}) == channels(ch5=255, ch22=128)


def test_option_with_several_channels_and_selected_segments():
    assert sent({'scan_speed': 1.0, 'draw_style': 'dots'}) == channels(ch10=255)
    assert sent({'move_x@b': -1.0, 'x_move_style@b': 'gap'}) == channels(ch32=255)


# ── Shared channels ──────────────────────────────────────────────────────

def test_a_moving_spin_wins_over_the_static_angle():
    result = renderer().render({'rot_z': 0.5, 'spin_z': 1.0})
    assert result.values[11] == 191 and result.ignored == (AttrKey('rot_z'),)


def test_a_spin_at_zero_hands_the_channel_back():
    result = renderer().render({'rot_z': 0.5, 'spin_z': 0.0})
    assert result.values[11] == 64 and result.ignored == ()                 # 63.5 rounds up


def test_one_wave_at_a_time():
    assert renderer().render({'wave_x': 1.0, 'wave_y': 1.0}).values[18] == 127
    result = renderer().render({'wave_x': 0.0, 'wave_y': 1.0})
    assert result.values[18] == 255 and result.ignored == ()
    assert renderer().render({'wave_x': 1.0, 'wave_y': 1.0}).ignored == (AttrKey('wave_y'),)


def test_colour_effects_win_over_fixed_colours():
    result = renderer().render({'color': 'red', 'x_flowing_water': 'water_2'})
    assert result.values[7] == 48 and result.ignored == (AttrKey('color'),)
    result = renderer().render({'color': 'red', 'color_effect': 'none'})
    assert result.values[7] == 8 and result.ignored == () and result.unsupported == ()


def test_the_bright_scan_takes_over_selector_and_speed():
    result = renderer().render({'draw_style': 'dots', 'scan_speed': 1.0, 'x_bright_scan': 1.0})
    assert result.values[9] == 63
    assert result.ignored == (AttrKey('draw_style'), AttrKey('scan_speed'))


def test_shared_channels_are_per_layer():
    result = renderer().render({'spin_z': 1.0, 'rot_z@b': 1.0})
    assert (result.values[11], result.values[28]) == (191, 127) and result.ignored == ()


# ── Portability ──────────────────────────────────────────────────────────

def test_what_this_fixture_cant_do_is_reported_not_refused():
    state = {'x_laser_2000_only': 3, 'size@c': 0.5, 'power@b': 'on', 'blackout': True,
             'color_effect': 'fade', 'size': 0.0}
    result = renderer().render(state)
    assert result.unsupported == tuple(AttrKey.parse(k) for k in ('x_laser_2000_only', 'size@c', 'power@b',
                                                                  'blackout', 'color_effect'))
    assert {ch: v for ch, v in enumerate(result.values, 1) if v != DEFAULTS[ch]} == {5: 255}


@pytest.mark.parametrize('state, message', [
    ({'size': 2}, 'size must be a number from 0 to 1'),
    ({'color': 'pink'}, 'color must be one of'),
    ({'size': 0.5, 'size@a': 0.2}, '"size" is given twice'),
    ({'Size': 0.5}, 'is not an attribute name'),
])
def test_wrong_values_for_known_attributes_are_bugs(state, message):
    with pytest.raises(ValueError, match=message):
        renderer().render(state)


# ── Patterns ─────────────────────────────────────────────────────────────

def test_patterns_render_per_layer_and_report_their_match():
    base = renderer().resolved
    library = base.binding.patterns.with_entry(
        PatternEntry('tunnel', {'Pattern Group': 64, 'Pattern Selection': 15}, 'tunnel'))
    r = compile_fixture(base.binding.with_patterns(library), base.profile)
    result = r.render({'pattern': PatternRequest.of('tunnel'), 'pattern@b': PatternRequest.of('star')})
    assert result.values[2:4] == bytes([64, 15]) and result.values[19:21] == bytes([0, 0])
    assert result.patterns['a'].name == 'tunnel' and result.patterns['b'] is None
    assert result.unsupported == result.ignored == ()                   # no match isn't a problem to report


def test_an_attribute_that_took_effect_somewhere_is_not_ignored():
    """draw_style and scan_speed drive two channels; losing one of them to
    an earlier mapping still leaves them working on the other."""
    linear = {'type': 'linear', 'attribute': 'scan_speed', 'channel': 'Gap', 'segment': 0}
    binding = load_binding({'version': 1, 'name': 'Two', 'profile': KEY, 'mode': '15ch', 'mappings': [
        {'type': 'linear', 'attribute': 'zoom', 'channel': 'Gap', 'segment': 0},
        {'type': 'selected', 'selector': 'draw_style', 'default': 'line',
         'choices': {'line': linear | {'channel': 'Size', 'segment': 0}}},
        {'type': 'selected', 'selector': 'draw_style', 'default': 'line', 'choices': {'line': linear}},
    ]})
    r = Renderer(binding.resolve(profile()))
    result = r.render({'zoom': 1.0, 'draw_style': 'line', 'scan_speed': 1.0})
    assert (result.values[1], result.values[6]) == (255, 99) and result.ignored == ()
    assert r.render({'zoom': 1.0, 'scan_speed': 1.0}).ignored == ()


# ── Base values and empty slots (the made-up fixture) ────────────────────

def test_base_values_beat_profile_defaults_and_empty_slots_send_zero():
    binding = load_binding({'version': 1, 'name': 'Tiny', 'profile': KEY, 'mode': '3ch', 'base': {'Power': 7},
                            'mappings': [{'type': 'linear', 'attribute': 'size', 'channel': 'Size'}]})
    r = Renderer(binding.resolve(profile()))
    assert r.defaults == bytes([7, 0, 0]) and r.layers == ('a',)
    assert r.render({'size': 1.0}).values == bytes([7, 255, 0])
    assert r.render({'size@b': 1.0}).unsupported == (AttrKey('size', 'b'),)
