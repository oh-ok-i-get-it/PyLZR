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


# ── Raw patterns (testers only) ──────────────────────────────────────────

GROUP_SELECTION = ('Pattern Group', 'Pattern Selection')      # the Gruolin's pattern channels: 3–4, b 20–21


def tagged_gruolin():
    base = renderer().resolved
    library = base.binding.patterns.with_entry(
        PatternEntry('tunnel 3', {'Pattern Group': 64, 'Pattern Selection': 15}, 'tunnel'))
    return compile_fixture(base.binding.with_patterns(library), base.profile)


def test_raw_patterns_set_each_layers_pattern_channels():
    result = renderer().render({'size': 0.5}, {'a': {'Pattern Group': 16, 'Pattern Selection': 25},
                                               'b': {'Pattern Group': 64, 'Pattern Selection': 3}})
    expected = bytearray(renderer().render({'size': 0.5}).values)
    expected[2:4], expected[19:21] = bytes([16, 25]), bytes([64, 3])            # only the pattern channels differ
    assert result.values == bytes(expected)
    assert dict(result.patterns) == {'a': None, 'b': None} and result.ignored == ()


def test_missing_raw_channels_take_no_pattern_then_the_default():
    values = renderer().render({}, {'a': {'Pattern Group': 32}}).values
    assert values[2:4] == bytes([32, 0])                       # Pattern Selection: the library's "none"
    values = renderer().render({}, {'b': {'Pattern Selection': 7}}).values
    assert values[19:21] == bytes([0, 7])                      # Pattern Group: its default


def test_raw_values_beat_a_request_which_is_reported_ignored():
    r = tagged_gruolin()
    result = r.render({'pattern': PatternRequest.of('tunnel'), 'pattern@b': PatternRequest.of('tunnel')},
                      {'a': {'Pattern Group': 16, 'Pattern Selection': 25}})
    assert result.values[2:4] == bytes([16, 25]) and result.values[19:21] == bytes([64, 15])
    assert result.ignored == (AttrKey('pattern'),)
    assert result.patterns['a'] is None and result.patterns['b'].name == 'tunnel 3'


def test_a_raw_pick_that_is_tagged_shows_its_tag():
    result = tagged_gruolin().render({}, {'b': {'Pattern Group': 64, 'Pattern Selection': 15}})
    assert result.patterns['b'].name == 'tunnel 3' and result.patterns['a'] is None


def sample_with_patterns():
    return Renderer(load_binding({'version': 1, 'name': 'Two', 'profile': KEY, 'mode': '15ch',
                                  'layers': {'a': 0, 'b': 7},
                                  'mappings': [{'type': 'linear', 'attribute': 'size', 'channel': 'Size'}],
                                  'patterns': {'channels': ['Pattern'], 'none': {'Pattern': 0}, 'library': []}},
                                 'test/two').resolve(profile()))


@pytest.mark.parametrize('raw, message', [
    ({'c': {'Pattern Group': 1}}, 'no layer "c"'),
    ({'a': {'Pattern Size': 1}}, '"Pattern Size" is not a pattern channel'),
    ({'a': {'Pattern Group': True}}, 'needs a DMX value'),
    ({'a': {'Pattern Group': 300}}, "isn't described by the profile"),
])
def test_bad_raw_patterns_are_refused(raw, message):
    with pytest.raises(ValueError, match=message):
        renderer().render({}, raw)


def test_raw_patterns_never_send_maintenance():
    r = sample_with_patterns()
    assert r.render({}, {'a': {'Pattern': 150}}).values[7] == 150            # a pattern on layer a …
    with pytest.raises(ValueError, match='Maintenance'):
        r.render({}, {'b': {'Pattern': 150}})                                # … Maintenance on layer b
    with pytest.raises(ValueError, match='Maintenance'):
        r.render({}, {'a': {'Pattern': 230}})


def test_a_fixture_without_patterns_takes_no_raw_patterns():
    r = Renderer(load_binding({'version': 1, 'name': 'Tiny', 'profile': KEY, 'mode': '3ch',
                               'mappings': [{'type': 'linear', 'attribute': 'size', 'channel': 'Size'}]}
                              ).resolve(profile()))
    assert r.pattern_channels() == () and r.library is None
    assert r.render({'size': 1.0}, {}).values == bytes([0, 255, 0])
    with pytest.raises(ValueError, match='no pattern channels'):
        r.render({}, {'a': {'Pattern': 1}})


def test_pattern_channels_list_what_a_raw_pattern_may_use():
    group, selection = renderer().pattern_channels()
    assert (group.name, selection.name) == GROUP_SELECTION
    assert [(s.start, s.end) for s in group.segments][:5] == [(0, 15), (16, 31), (32, 47), (48, 63), (64, 127)]
    assert group.segments[1].label == 'Line patterns, folder 2' and len(group.segments) == 9
    assert [(s.start, s.end, s.label) for s in selection.segments] == [(0, 0, 'No pattern'), (1, 255, 'Pattern')]
    group_b, selection_b = renderer().pattern_channels('b')
    assert group_b.segments[:5] == group.segments[:5]                       # each layer's own segments:
    assert [(s.start, s.end, s.label) for s in group_b.segments[5:]] == [(128, 255, 'Generic')]  # no dynamic effects
    assert selection_b.segments[0].label == 'No second pattern'
    a, b = sample_with_patterns().pattern_channels('a'), sample_with_patterns().pattern_channels('b')
    assert [(s.start, s.end) for s in a[0].segments] == [(0, 0), (1, 199)]  # Maintenance left out
    assert [(s.start, s.end) for s in b[0].segments] == [(0, 0), (1, 99)]   # layer b has fewer patterns
    assert b[0].allows(99) and not b[0].allows(100)


def test_a_different_laser_one_layer_and_mode_based_patterns():
    import el400
    r = el400.renderer()
    assert r.layers == ('a',) and not r.supports('power') and r.supports('x_dynamic_speed')
    mode, selection = r.pattern_channels()
    assert [s.label for s in mode.segments] == ['Laser off', 'Sound mode', 'Automatic mode', 'Static pattern',
                                                'Dynamic pattern']
    result = r.render({'color': 'red'}, {'a': {'Mode': 160, 'Pattern Selection': 20}})
    assert result.values[:2] == bytes([160, 20]) and result.values[7] == 12
    assert r.render({}).values[0] == 0                                       # no pattern: laser off


def test_a_missing_raw_channel_takes_the_librarys_no_pattern_value_over_the_default():
    r = Renderer(load_binding({'version': 1, 'name': 'Odd', 'profile': KEY, 'mode': '15ch', 'layers': {'a': 0, 'b': 7},
                               'mappings': [{'type': 'linear', 'attribute': 'size', 'channel': 'Size'}],
                               'patterns': {'channels': ['Pattern'], 'none': {'Pattern': 5}, 'library': []}},
                              'test/odd').resolve(profile()))
    assert r.defaults[7] == 0                                                # the channel's default …
    assert r.render({}, {'a': {}}).values[7] == 5                            # … loses to "no pattern"
