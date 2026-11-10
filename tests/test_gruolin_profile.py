"""The shipped Gruolin RGB Fullcolor Beam Effect Light profile: loaded as a
package resource, complete, both outputs alike, and holding what was checked
on the laser (Nov 2026)."""

import re
from importlib.resources import as_file, files

import pytest

from pylzr.fixtures import parse_entity, read_profile

KEY = 'gruolin/rgb-fullcolor-beam-effect-light'

# Channels 5–19 (first pattern); 22–36 are the same with " 2"
PATTERN_CHANNELS = ['Pattern Size', 'Horizontal Position', 'Vertical Position', 'Color', 'Color Speed',
                    'Scan Speed', 'Strobe', 'Rotation Z', 'Rotation X', 'Rotation Y', 'Horizontal Movement',
                    'Vertical Movement', 'Zoom', 'Gradient Speed', 'Wave']

OFL_CATEGORIES = {'Barrel Scanner', 'Blinder', 'Color Changer', 'Dimmer', 'Effect', 'Fan', 'Flower', 'Hazer',
                  'Laser', 'Matrix', 'Moving Head', 'Pixel Bar', 'Scanner', 'Smoke', 'Stand', 'Strobe', 'Other'}


@pytest.fixture(scope='module')
def gruolin():
    resource = files('pylzr.fixtures') / 'data' / 'profiles' / f'{KEY}.json'
    with as_file(resource) as path:
        return read_profile(path, KEY)


def channel(profile, name):
    return profile.channels[name]


def ranges(profile, name):
    return [(c.start, c.end) for c in channel(profile, name).capabilities]


# ── Shape ────────────────────────────────────────────────────────────────

def test_identity(gruolin):
    assert (gruolin.key, gruolin.name, gruolin.short_name) == (
        KEY, 'RGB Fullcolor Beam Effect Light', 'Gruolin RGB Beam')
    assert gruolin.categories == ('Laser',)


def test_modes_follow_the_manual(gruolin):
    assert gruolin.mode('36ch').channels == (
        'On/Off', 'Auto Speed', 'Pattern Group', 'Pattern Selection', *PATTERN_CHANNELS,
        'Pattern Group 2', 'Pattern Selection 2', *[f'{c} 2' for c in PATTERN_CHANNELS])
    assert gruolin.mode('16ch').channels == (
        'On/Off', 'Auto Speed', 'Pattern Group', 'Pattern Selection', 'Color', 'Color Speed', 'Scan Speed',
        'Pattern Size', 'Rotation Z', 'Rotation X', 'Rotation Y', 'Horizontal Movement', 'Vertical Movement',
        'Zoom', 'Gradient Speed', 'Wave')
    assert [(m.name, m.footprint) for m in gruolin.modes] == [('16-channel', 16), ('36-channel', 36)]


def test_every_channel_describes_every_value(gruolin):
    """0–255 covered on every channel, with no gaps."""
    for name in gruolin.channels:
        spans = ranges(gruolin, name)
        assert spans[0][0] == 0 and spans[-1][1] == 255, name
        assert all(after[0] == before[1] + 1 for before, after in zip(spans, spans[1:], strict=False)), name


def test_second_pattern_matches_the_first(gruolin):
    for name in PATTERN_CHANNELS:
        first, second = channel(gruolin, name), channel(gruolin, f'{name} 2')
        assert (second.capabilities, second.default_value) == (first.capabilities, first.default_value), name


def test_only_the_first_pattern_has_dynamic_effects(gruolin):
    first, second = channel(gruolin, 'Pattern Group'), channel(gruolin, 'Pattern Group 2')
    assert first.capabilities[:5] == second.capabilities[:5]            # line folders + animation, 0–127
    assert [c.properties.get('effectName', '') for c in first.capabilities[5:]] == [
        'Dynamic line effects, folder 1', 'Dynamic line effects, folder 2', 'Dynamic animation effects',
        'Dynamic line effects, folder 3']
    assert ranges(gruolin, 'Pattern Group 2')[5:] == [(128, 255)]
    assert second.capability_at(200).type == 'Generic'


# ── What was checked on the laser ────────────────────────────────────────

def test_on_off_has_no_dimming(gruolin):
    on_off = channel(gruolin, 'On/Off')
    assert on_off.capability_at(0).properties['shutterEffect'] == 'Closed'
    assert on_off.capability_at(1) is on_off.capability_at(255)
    assert on_off.capability_at(255).properties['shutterEffect'] == 'Open'


def test_colours(gruolin):
    color = channel(gruolin, 'Color')
    assert color.capability_at(0).properties['colors'] == ['#ffffff']
    assert 'colors' not in color.capability_at(1).properties                  # original colours
    fixed = [color.capability_at(value).properties['colors'][0] for value in range(4, 32, 4)]
    assert fixed == ['#ffffff', '#ff0000', '#ffff00', '#00ff00', '#00ffff', '#0000ff', '#ff00ff']
    assert [color.capability_at(v).end - color.capability_at(v).start for v in range(4, 32, 4)] == [3] * 7


def test_flowing_water_effects(gruolin):
    flows = [c for c in channel(gruolin, 'Color').capabilities
             if c.properties.get('effectName', '').startswith('Flowing water')]
    assert len(flows) == 49
    assert [(c.start, c.end) for c in flows] == [(44 + 4 * i, 47 + 4 * i) for i in range(49)]
    assert flows[-1].properties['effectName'] == 'Flowing water 49'


def test_rotation_angle_then_spin_both_ways(gruolin):
    for axis in 'ZXY':
        rot = channel(gruolin, f'Rotation {axis}')
        assert ranges(gruolin, f'Rotation {axis}') == [(0, 127), (128, 191), (192, 255)]
        angle, clockwise, anticlockwise = rot.capabilities
        assert angle.span('angle') == ('0deg', '360deg')
        assert [parse_entity(v).number for v in clockwise.span('speed')] == [1, 100]       # slow CW → fast CW
        assert [parse_entity(v).number for v in anticlockwise.span('speed')] == [-1, -100]


def test_movement_position_and_scrolls(gruolin):
    for axis in ('Horizontal', 'Vertical'):
        move = channel(gruolin, f'{axis} Movement')
        assert ranges(gruolin, f'{axis} Movement') == [
            (0, 0), (1, 127), (128, 159), (160, 191), (192, 223), (224, 255)]
        assert move.capability_at(0).type == 'BeamPosition' and move.capability_at(64).proportional
        names = [c.properties.get('effectName') for c in move.capabilities[2:]]
        assert names == [f'{axis} scroll, edge to edge, inner to outer', f'{axis} scroll, edge to edge, outer to inner',
                         f'{axis} scroll with a gap, inner to outer', f'{axis} scroll with a gap, outer to inner']


def test_zoom_static_then_loops(gruolin):
    zoom = channel(gruolin, 'Zoom')
    assert ranges(gruolin, 'Zoom') == [(0, 127), (128, 159), (160, 191), (192, 223), (224, 255)]
    assert zoom.capability_at(0).span('angle') == ('wide', 'narrow')           # full size → a dot
    assert [c.properties['effectName'] for c in zoom.capabilities[1:]] == [
        'Zoom in loop', 'Zoom out loop', 'Zoom pulse', 'Zoom pulse 2']


def test_zero_is_no_effect(gruolin):
    assert channel(gruolin, 'Strobe').capability_at(0).properties['shutterEffect'] == 'Open'
    for name in ('Gradient Speed', 'Wave'):
        assert channel(gruolin, name).capability_at(0).properties['speed'] == 'stop'
    assert channel(gruolin, 'Horizontal Movement').capability_at(0).properties['horizontalAngle'] == 'center'


def test_pattern_number_zero_hides_that_pattern(gruolin):
    for name in ('Pattern Selection', 'Pattern Selection 2'):
        sel = channel(gruolin, name)
        assert ranges(gruolin, name) == [(0, 0), (1, 255)]
        assert sel.capability_at(0).comment.startswith('No ') and 'stays dark' in sel.capability_at(0).comment


def test_positions_start_centred(gruolin):
    """The pattern only shows near 128 (manual, and checked)."""
    for name in ('Horizontal Position', 'Vertical Position', 'Horizontal Position 2', 'Vertical Position 2'):
        assert channel(gruolin, name).default_value == 128
    assert channel(gruolin, 'Pattern Size').default_value == 0


def test_assumptions_are_marked(gruolin):
    """What wasn't checked on the laser carries OFL's helpWanted."""
    def help_wanted(name, value):
        return bool(channel(gruolin, name).capability_at(value).help_wanted)

    assert not help_wanted('Rotation Z', 50) and help_wanted('Rotation X', 50) and help_wanted('Rotation Y', 50)
    assert not help_wanted('Horizontal Movement', 50) and help_wanted('Vertical Movement', 50)
    assert help_wanted('Pattern Group', 0) and not help_wanted('Pattern Group', 20)


# ── Valid OFL (so it could be submitted later) ───────────────────────────

def test_follows_ofl_rules_the_reader_doesnt_need(gruolin):
    assert set(gruolin.categories) <= OFL_CATEGORIES
    assert all('mode' not in m.name.lower() for m in gruolin.modes)
    for ch in gruolin.channels.values():
        for cap in ch.capabilities:
            for color in cap.properties.get('colors', []):
                assert re.fullmatch(r'#[0-9a-f]{6}', color)
