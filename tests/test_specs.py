"""Mapping specs (pylzr.fixtures.specs): reading them from a binding file,
writing them back, and building mappings from the profile's segments."""

import pytest
from sample_fixture import profile

from pylzr.fixtures import (
    SPEC_TYPES, Bipolar, BindingError, BipolarSpec, Direction, DirectionSpec, Linear, LinearSpec, Options,
    OptionsSpec, Selected, SelectedSpec, read_spec,
)
from pylzr.fixtures.jsonio import ObjectReader
from pylzr.fixtures.specs import ends


@pytest.fixture(scope='module')
def channels():
    return dict(profile().channels)


def read(data):
    return read_spec(ObjectReader(data, 'mappings[0]', BindingError))


def build(data, channels):
    return read(data).build(channels)


def segment(channels, name, at):
    return channels[name].capability_at(at)


# ── Segment direction ────────────────────────────────────────────────────

def test_ends_follow_the_profile(channels):
    assert ends(segment(channels, 'Spin', 128)) == (128, 191)        # slow CW → fast CW
    assert ends(segment(channels, 'Spin', 200)) == (255, 192)        # fast CCW → slow CCW: slow is at 255
    assert ends(segment(channels, 'Spin', 0)) == (0, 127)            # an angle: low → high
    assert ends(segment(channels, 'Size', 0)) == (0, 255)


# ── Building ─────────────────────────────────────────────────────────────

def test_linear_takes_its_ends_from_the_segment(channels):
    assert build({'type': 'linear', 'attribute': 'size', 'channel': 'Size'}, channels) == Linear(
        'size', 'Size', 0, 255)
    assert build({'type': 'linear', 'attribute': 'size', 'channel': 'Size', 'invert': True, 'min': 0.1,
                  'max': 0.9}, channels) == Linear('size', 'Size', 255, 0, 0.1, 0.9)
    assert build({'type': 'linear', 'attribute': 'strobe', 'channel': 'Strobe', 'segment': 10, 'zero': 0},
                 channels) == Linear('strobe', 'Strobe', 10, 255, zero=0)
    assert build({'type': 'linear', 'attribute': 'wave_x', 'channel': 'Gap', 'segment': 50, 'zero': 'release'},
                 channels) == Linear('wave_x', 'Gap', 0, 99, release_at_zero=True)


def test_a_speed_segment_runs_slow_to_fast_whichever_way_the_profile_writes_it(channels):
    assert build({'type': 'linear', 'attribute': 'scan_speed', 'channel': 'Spin', 'segment': 192},
                 channels) == Linear('scan_speed', 'Spin', 255, 192)


def test_bipolar_and_direction(channels):
    assert build({'type': 'bipolar', 'attribute': 'pos_x', 'channel': 'Position', 'centre': 128, 'limit': 0.5},
                 channels) == Bipolar('pos_x', 'Position', 0, 128, 255, 0.5)
    assert build({'type': 'bipolar', 'attribute': 'pos_x', 'channel': 'Position', 'centre': 100, 'invert': True},
                 channels) == Bipolar('pos_x', 'Position', 255, 100, 0)
    assert build({'type': 'direction', 'attribute': 'spin_z', 'channel': 'Spin', 'forward': 128, 'reverse': 192,
                  'off': 0, 'deadband': 0.1}, channels) == Direction(
        'spin_z', 'Spin', (128, 191), (255, 192), off=0, deadband=0.1)


def test_options_and_selected(channels):
    assert build({'type': 'options', 'attribute': 'color', 'values': {'white': {'Colour': 0}, 'red': {'Colour': 8}}},
                 channels) == Options('color', {'white': {'Colour': 0}, 'red': {'Colour': 8}})
    built = build({'type': 'selected', 'selector': 'draw_style', 'default': 'line', 'choices': {
        'line': {'type': 'linear', 'attribute': 'scan_speed', 'channel': 'Spin', 'segment': 128},
        'dots': {'type': 'linear', 'attribute': 'scan_speed', 'channel': 'Spin', 'segment': 192}}}, channels)
    assert built == Selected('draw_style', {'line': Linear('scan_speed', 'Spin', 128, 191),
                                            'dots': Linear('scan_speed', 'Spin', 255, 192)}, 'line')


@pytest.mark.parametrize('data, where, message', [
    ({'type': 'linear', 'attribute': 'size', 'channel': 'Sise'}, 'channel', 'no channel "Sise" .*did you mean "Size"'),
    ({'type': 'linear', 'attribute': 'rot_z', 'channel': 'Spin'}, 'segment', '"Spin" has 3 segments: say which'),
    ({'type': 'linear', 'attribute': 'x_wobble', 'channel': 'Gap', 'segment': 150}, 'segment',
     '"Gap" has no segment at 150'),
    ({'type': 'linear', 'attribute': 'x_red', 'channel': 'Colour', 'segment': 8}, 'segment',
     'segment 8–15 of "Colour" is a single step .*use an options mapping'),
    ({'type': 'linear', 'attribute': 'strobe', 'channel': 'Strobe', 'segment': 0}, 'segment',
     'is a single step \\(NoFunction\\)'),
    ({'type': 'linear', 'attribute': 'size', 'channel': 'Size', 'min': 0.9, 'max': 0.1}, '', 'min .* is above max'),
    ({'type': 'bipolar', 'attribute': 'pos_x', 'channel': 'Spin', 'segment': 0, 'centre': 200}, 'centre',
     '200 is outside the segment 0–127'),
    ({'type': 'bipolar', 'attribute': 'pos_x', 'channel': 'Position', 'centre': 128, 'limit': 0}, '',
     'limit must be above 0'),
    ({'type': 'direction', 'attribute': 'spin_z', 'channel': 'Spin', 'forward': 128, 'reverse': 150}, 'reverse',
     'forward and reverse are the same segment'),
    ({'type': 'direction', 'attribute': 'spin_z', 'channel': 'Colour', 'forward': 0, 'reverse': 16}, 'forward',
     'single step'),
    ({'type': 'options', 'attribute': 'color', 'values': {'red': {'Color': 8}}}, 'values.red.Color',
     'no channel "Color"'),
    ({'type': 'options', 'attribute': 'color', 'values': {'red': {}}}, '', 'choice "red" sets no channel'),
    ({'type': 'options', 'attribute': 'color', 'values': {}}, '', 'needs at least one choice'),
    ({'type': 'selected', 'selector': 'draw_style', 'default': 'line', 'choices': {
        'line': {'type': 'linear', 'attribute': 'scan_speed', 'channel': 'Spin'}}}, 'choices.line.segment',
     'say which'),
    ({'type': 'selected', 'selector': 'draw_style', 'default': 'dots', 'choices': {
        'line': {'type': 'linear', 'attribute': 'scan_speed', 'channel': 'Size'}}}, '', 'default "dots"'),
])
def test_build_errors_name_their_place(data, where, message, channels):
    with pytest.raises(BindingError, match=message) as info:
        build(data, channels)
    assert info.value.where == where


# ── Reading and writing ──────────────────────────────────────────────────

CANONICAL = [
    {'type': 'linear', 'attribute': 'size', 'channel': 'Size'},
    {'type': 'linear', 'attribute': 'size', 'channel': 'Size', 'segment': 0, 'invert': True, 'min': 0.1, 'max': 0.9,
     'zero': 3, 'comment': 'all of it'},
    {'type': 'linear', 'attribute': 'wave_x', 'channel': 'Gap', 'segment': 0, 'zero': 'release'},
    {'type': 'bipolar', 'attribute': 'pos_x', 'channel': 'Position', 'centre': 128},
    {'type': 'bipolar', 'attribute': 'pos_x', 'channel': 'Position', 'segment': 0, 'centre': 128, 'limit': 0.5,
     'invert': True, 'comment': 'c'},
    {'type': 'direction', 'attribute': 'spin_z', 'channel': 'Spin', 'forward': 128, 'reverse': 192},
    {'type': 'direction', 'attribute': 'spin_z', 'channel': 'Spin', 'forward': 128, 'reverse': 192, 'off': 0,
     'deadband': 0.05, 'comment': 'c'},
    {'type': 'options', 'attribute': 'power', 'values': {'off': {'Power': 0}, 'on': {'Power': 255}}, 'comment': 'c'},
    {'type': 'selected', 'selector': 'draw_style', 'default': 'line', 'choices': {
        'line': {'type': 'linear', 'attribute': 'scan_speed', 'channel': 'Spin', 'segment': 128}}, 'comment': 'c'},
]


@pytest.mark.parametrize('data', CANONICAL)
def test_round_trip(data):
    spec = read(data)
    assert spec.to_json() == data
    assert read(spec.to_json()) == spec


def test_defaults_are_left_out_when_saving():
    data = {'type': 'linear', 'attribute': 'size', 'channel': 'Size', 'invert': False, 'min': 0, 'max': 1,
            'comment': ''}
    assert read(data).to_json() == {'type': 'linear', 'attribute': 'size', 'channel': 'Size'}
    assert read({'type': 'direction', 'attribute': 'spin_z', 'channel': 'Spin', 'forward': 128, 'reverse': 192,
                 'deadband': 0}).to_json() == CANONICAL[5]


def test_specs_are_read_only():
    spec = read(CANONICAL[7])
    with pytest.raises(TypeError):
        spec.values['on']['Power'] = 1                                        # type: ignore[index]
    with pytest.raises(AttributeError):
        spec.attribute = 'x'                                                  # type: ignore[misc]


def test_every_type_is_registered():
    assert dict(SPEC_TYPES) == {'linear': LinearSpec, 'bipolar': BipolarSpec, 'direction': DirectionSpec,
                                'options': OptionsSpec, 'selected': SelectedSpec}


@pytest.mark.parametrize('data, where, message', [
    ({'type': 'lineer', 'attribute': 'size', 'channel': 'Size'}, 'mappings[0].type',
     'unknown mapping type "lineer" \\(did you mean "linear"\\?\\)'),
    ({'type': 'curve'}, 'mappings[0].type', 'one of: linear, bipolar, direction, options, selected'),
    ({'attribute': 'size'}, 'mappings[0]', '"type" is missing'),
    ({'type': 'linear', 'attribute': 'size', 'channel': 'Size', 'centr': 1}, 'mappings[0]', 'unknown key "centr"'),
    ({'type': 'linear', 'attribute': 'Size', 'channel': 'Size'}, 'mappings[0].attribute', 'not an attribute name'),
    ({'type': 'linear', 'attribute': 'size', 'channel': 'Size', 'segment': 300}, 'mappings[0].segment',
     'must be a DMX value'),
    ({'type': 'linear', 'attribute': 'size', 'channel': 'Size', 'zero': 'off'}, 'mappings[0].zero',
     'must be a DMX value or "release"'),
    ({'type': 'linear', 'attribute': 'size', 'channel': 'Size', 'zero': -1}, 'mappings[0].zero', 'DMX value'),
    ({'type': 'linear', 'attribute': 'size', 'channel': 'Size', 'invert': 'yes'}, 'mappings[0].invert',
     'must be true or false'),
    ({'type': 'bipolar', 'attribute': 'pos_x', 'channel': 'Position'}, 'mappings[0]', '"centre" is missing'),
    ({'type': 'direction', 'attribute': 'spin_z', 'channel': 'Spin', 'forward': 128}, 'mappings[0]',
     '"reverse" is missing'),
    ({'type': 'options', 'attribute': 'color', 'values': {'Red': {'Colour': 8}}}, 'mappings[0].values.Red',
     'not a choice name'),
    ({'type': 'options', 'attribute': 'color', 'values': {'red': {'Colour': 'x'}}}, 'mappings[0].values.red.Colour',
     'must be a whole number'),
    ({'type': 'options', 'attribute': 'color', 'values': {'red': {'Colour': 256}}}, 'mappings[0].values.red.Colour',
     'must be a DMX value'),
    ({'type': 'selected', 'selector': 'draw_style', 'default': 'line', 'choices': {
        'line': {'type': 'linear', 'attribute': 'scan_speed'}}}, 'mappings[0].choices.line', '"channel" is missing'),
    ({'type': 'selected', 'selector': 'draw_style', 'default': 'line', 'choices': {
        'Line': {'type': 'linear', 'attribute': 'scan_speed', 'channel': 'Size'}}}, 'mappings[0].choices.Line',
     'not a choice name'),
])
def test_read_errors_name_their_place(data, where, message):
    with pytest.raises(BindingError, match=message) as info:
        read(data)
    assert info.value.where == where
