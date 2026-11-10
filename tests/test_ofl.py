"""Open Fixture Library profiles (pylzr.fixtures.ofl): a real profile from the
OFL (tests/data/ofl, MIT), then synthetic ones for each rule."""

import json
from pathlib import Path

import pytest

from pylzr.fixtures import ProfileError
from pylzr.fixtures.ofl import CAPABILITY_TYPES, Entity, load_profile, parse_entity, read_profile

EL400 = Path(__file__).parent / 'data' / 'ofl' / 'laserworld' / 'el-400rgb-mk2.json'


def profile_data(channels: dict, modes: list | None = None, **top) -> dict:
    """Minimal valid OFL data around `channels` (one mode with all of them)."""
    return {
        'name': 'Test Laser', 'categories': ['Laser'], 'meta': {'authors': ['test']},
        'availableChannels': channels,
        'modes': modes if modes is not None else [{'name': '2-channel', 'shortName': '2ch',
                                                   'channels': list(channels)}],
        **top,
    }


def one_channel(**channel) -> dict:
    return profile_data({'Dimmer': channel}, [{'name': '1-channel', 'channels': ['Dimmer']}])


# ── A real profile ───────────────────────────────────────────────────────

@pytest.fixture(scope='module')
def el400():
    return read_profile(EL400, 'laserworld/el-400rgb-mk2')


def test_real_profile_basics(el400):
    assert (el400.key, el400.name, el400.short_name) == ('laserworld/el-400rgb-mk2', 'EL-400RGB MK2', 'EL-400RGB MK2')
    assert el400.categories == ('Laser', 'Color Changer')
    assert list(el400.channels) == ['Mode', 'Pattern Selection', 'Horizontal Angle', 'Vertical Angle',
                                    'Scanning Speed', 'Dynamic Pattern Speed', 'Zoom', 'Color', 'Color Segment']


def test_real_profile_mode(el400):
    mode = el400.mode('9ch')
    assert el400.mode('9-channel') is mode
    assert mode.footprint == 9
    assert mode.offset('Zoom') == 6
    with pytest.raises(KeyError, match='has no channel "Strobe"'):
        mode.offset('Strobe')
    with pytest.raises(KeyError, match=r'has no mode "36ch" \(it has: 9ch\)'):
        el400.mode('36ch')


def test_real_profile_capabilities(el400):
    mode = el400.channels['Mode']
    assert [(c.start, c.end, c.type) for c in mode.capabilities][:2] == [(0, 49, 'NoFunction'), (50, 99, 'Effect')]
    assert mode.capability_at(120).properties['effectName'] == 'Automatic mode'

    color = el400.channels['Color']
    assert len(color.capabilities) == 44
    assert color.capability_at(12).comment == 'Red'
    assert color.capability_at(255).properties['colors'] == ['#ffffff']
    assert (color.capabilities[0].start, color.capabilities[-1].end) == (0, 255)

    pattern = el400.channels['Pattern Selection'].capabilities
    assert [(c.start, c.end, c.type) for c in pattern] == [(0, 255, 'Effect')]   # single capability: whole range


def test_real_profile_proportional_properties(el400):
    position = el400.channels['Horizontal Angle']
    centre, sweep = position.capabilities
    assert not centre.proportional and sweep.proportional
    assert centre.span('horizontalAngle') == ('center', 'center')
    assert sweep.span('horizontalAngle') == ('left', 'right')
    assert [parse_entity(v) for v in sweep.span('horizontalAngle')] == [Entity(-100, '%'), Entity(100, '%')]
    speed = el400.channels['Scanning Speed'].capabilities[0]
    assert [parse_entity(v).number for v in speed.span('speed')] == [100, 1]          # fast → slow
    assert speed.span('angle') is None


def test_properties_are_read_only(el400):
    with pytest.raises(TypeError):
        el400.channels['Zoom'].capabilities[0].properties['angleStart'] = 'wide'    # type: ignore[index]
    with pytest.raises(TypeError):
        el400.channels['Extra'] = None                                              # type: ignore[index]


# ── Entities ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize('value, entity', [
    ('fast', Entity(100, '%')), ('slow', Entity(1, '%')), ('stop', Entity(0, '%')),
    ('fast reverse', Entity(-100, '%')), ('slow CCW', Entity(-1, '%')), ('fast CW', Entity(100, '%')),
    ('left', Entity(-100, '%')), ('center', Entity(0, '%')), ('narrow', Entity(1, '%')),
    ('50%', Entity(50, '%')), ('10.5Hz', Entity(10.5, 'Hz')), ('120bpm', Entity(120, 'bpm')),
    ('-10deg', Entity(-10, 'deg')), ('530deg', Entity(530, 'deg')), ('300ms', Entity(300, 'ms')),
    ('2s', Entity(2, 's')), ('3200K', Entity(3200, 'K')), ('5m^3/min', Entity(5, 'm^3/min')),
    (3, Entity(3, '')), (2.5, Entity(2.5, '')), ('7', Entity(7, '')),
])
def test_entities(value, entity):
    assert parse_entity(value) == entity


@pytest.mark.parametrize('value', ['fats', 'Fast', '10 Hz', '10hz', 'deg', '', True, None, [1]])
def test_bad_entities(value):
    with pytest.raises(ValueError, match='is not an OFL value'):
        parse_entity(value)


# ── Channels and capabilities ────────────────────────────────────────────

def test_capabilities_with_gaps_leave_values_unknown():
    profile = load_profile(one_channel(capabilities=[
        {'dmxRange': [0, 9], 'type': 'NoFunction'},
        {'dmxRange': [20, 255], 'type': 'Intensity', 'brightnessStart': 'dark', 'brightnessEnd': 'bright'},
    ]))
    channel = profile.channels['Dimmer']
    assert channel.capability_at(5).type == 'NoFunction'
    assert channel.capability_at(15) is None
    assert channel.capability_at(20).type == 'Intensity'
    assert channel.default_value == 0


@pytest.mark.parametrize('default, value', [(128, 128), ('50%', 128), ('100%', 255), ('0%', 0)])
def test_default_value(default, value):
    profile = load_profile(one_channel(capability={'type': 'Intensity'}, defaultValue=default))
    assert profile.channels['Dimmer'].default_value == value


@pytest.mark.parametrize('channel, message', [
    ({}, '^availableChannels.Dimmer: needs either "capability" or "capabilities"'),
    ({'capability': {'type': 'Intensity'}, 'capabilities': []}, 'needs either'),
    ({'capabilities': []}, r'^availableChannels\.Dimmer\.capabilities: needs at least one capability'),
    ({'capabilities': [{'type': 'Intensity'}]}, r'capabilities\[0\]: "dmxRange" is missing'),
    ({'capabilities': [{'dmxRange': [0, 300], 'type': 'Intensity'}]}, r'capabilities\[0\]\.dmxRange: must be'),
    ({'capabilities': [{'dmxRange': [9, 3], 'type': 'Intensity'}]}, r'dmxRange: must be \[first, last\]'),
    ({'capabilities': [{'dmxRange': [0, 1.5], 'type': 'Intensity'}]}, 'dmxRange: must be'),
    ({'capabilities': [{'dmxRange': [0, 10], 'type': 'Intensity'}, {'dmxRange': [10, 255], 'type': 'Generic'}]},
     r'capabilities\[1\]: range 10–255 must start after the previous one \(0–10\)'),
    ({'capabilities': [{'dmxRange': [50, 99], 'type': 'Intensity'}, {'dmxRange': [0, 9], 'type': 'Generic'}]},
     r'capabilities\[1\]: range 0–9 must start after'),
    ({'capability': {'type': 'Strobe'}}, r'capability\.type: unknown capability type "Strobe"'),
    ({'capability': {'type': 'Zom'}}, r'unknown capability type "Zom" \(did you mean "Zoom"\?\)'),
    ({'capability': {'type': 'Speed', 'speedStrat': 'fast', 'speedEnd': 'slow'}},
     r'capability\.speedStrat: unknown capability property "speedStrat" \(did you mean "speedStart"\?\)'),
    ({'capability': {'type': 'Speed', 'speedStart': 'fast'}}, r'speedStart: "speedStart" needs "speedEnd" too'),
    ({'capability': {'type': 'Speed', 'speed': 'fast', 'speedStart': 'fast', 'speedEnd': 'slow'}},
     '"speed" can\'t be given with'),
    ({'capability': {'type': 'Speed', 'speedStart': 'fats', 'speedEnd': 'slow'}},
     r'capability\.speedStart: the text "fats" is not an OFL value'),
    ({'capability': {'type': 'Intensity', 'menuClick': 'middle'}}, 'must be start, center, end or hidden'),
    ({'capability': {'type': 'Intensity'}, 'defaultValue': 256}, r'defaultValue: must be 0–255, not 256'),
    ({'capability': {'type': 'Intensity'}, 'defaultValue': '120%'}, 'must be 0–255 or a percentage'),
    ({'capability': {'type': 'Intensity'}, 'precedence': 'FIFO'}, 'must be HTP or LTP'),
    ({'capability': {'type': 'Intensity'}, 'capabilty': 1}, 'unknown key "capabilty"'),
])
def test_bad_channels_say_where(channel, message):
    with pytest.raises(ProfileError, match=message):
        load_profile(one_channel(**channel))


@pytest.mark.parametrize('channel, what', [
    ({'capability': {'type': 'Intensity'}, 'fineChannelAliases': ['Dimmer fine']}, '16-bit channels'),
    ({'capability': {'type': 'Intensity'}, 'dmxValueResolution': '16bit'}, 'dmxValueResolution "16bit"'),
    ({'capability': {'type': 'Effect', 'effectName': 'x', 'switchChannels': {'A': 'B'}}}, 'switching channels'),
])
def test_unsupported_channel_features_are_named(channel, what):
    with pytest.raises(ProfileError, match=what):
        load_profile(one_channel(**channel))


@pytest.mark.parametrize('top', [{'matrix': {'pixelCount': [5, 1, 1]}}, {'templateChannels': {}}])
def test_pixel_fixtures_are_refused(top):
    with pytest.raises(ProfileError, match="pixel fixtures .* which PyLZR doesn't support yet"):
        load_profile(one_channel(capability={'type': 'Intensity'}) | top)


def test_every_capability_type_is_known():
    assert len(CAPABILITY_TYPES) == len(set(CAPABILITY_TYPES)) == 43
    for kind in CAPABILITY_TYPES:
        load_profile(one_channel(capability={'type': kind}))


# ── Profile and modes ────────────────────────────────────────────────────

def test_modes_with_unused_slots():
    channels = {'A': {'capability': {'type': 'Intensity'}}, 'B': {'capability': {'type': 'Generic'}}}
    profile = load_profile(profile_data(channels, [
        {'name': '3-channel', 'shortName': '3ch', 'channels': ['A', None, 'B']},
        {'name': '1-channel', 'channels': ['B']},
    ], shortName='TL'))
    three = profile.mode('3ch')
    assert (three.channels, three.footprint, three.offset('B')) == (('A', None, 'B'), 3, 2)
    assert profile.mode('1-channel').short_name == '1-channel'                  # defaults to the name
    assert profile.short_name == 'TL' and profile.key == ''


def test_extra_metadata_is_allowed():
    data = one_channel(capability={'type': 'Intensity'})
    data.update({'$schema': 'x', 'comment': 'c', 'helpWanted': 'h', 'links': {'manual': ['u']},
                 'rdm': {'modelId': 1}, 'physical': {'weight': 3}, 'wheels': {}})
    data['modes'][0].update({'rdmPersonalityIndex': 1, 'physical': {'power': 30}})
    assert load_profile(data).name == 'Test Laser'


@pytest.mark.parametrize('change, message', [
    (lambda d: d.pop('name'), '^"name" is missing'),
    (lambda d: d.update(categories=[]), '^categories: needs at least one category'),
    (lambda d: d.update(categories=['Laser', 5]), r'^categories\[1\]: must be text'),
    (lambda d: d.update(availableChannels={}), '^availableChannels: needs at least one channel'),
    (lambda d: d.update(modes=[]), '^modes: needs at least one mode'),
    (lambda d: d['modes'][0].update(channels=['Dimer']),
     r'^modes\[0\]\.channels\[0\]: no channel "Dimer" in availableChannels \(did you mean "Dimmer"\?\)'),
    (lambda d: d['modes'][0].update(channels=['Dimmer', 'Dimmer']), r'channels\[1\]: channel "Dimmer" is used twice'),
    (lambda d: d['modes'][0].update(channels=[]), r'^modes\[0\]\.channels: needs at least one channel'),
    (lambda d: d['modes'][0].update(channels=[{'insert': 'matrixChannels'}]), 'matrix channel inserts'),
    (lambda d: d['modes'].append({'name': '1-channel', 'channels': ['Dimmer']}),
     r'^modes\[1\]: two modes have the name "1-channel"'),
    (lambda d: d['modes'][0].pop('name'), r'^modes\[0\]: "name" is missing'),
    (lambda d: d['modes'].append({'name': 'other', 'shortName': '1-channel', 'channels': ['Dimmer']}),
     r'^modes\[1\]: two modes have the shortName "1-channel"'),       # bindings pick modes by short name
    (lambda d: d.update(fixtureKey='x'), '^unknown key "fixtureKey"'),
])
def test_bad_profiles_say_where(change, message):
    data = one_channel(capability={'type': 'Intensity'})
    change(data)
    with pytest.raises(ProfileError, match=message):
        load_profile(data)


def test_read_profile_names_the_file(tmp_path):
    path = tmp_path / 'broken.json'
    path.write_text(json.dumps(one_channel(capability={'type': 'Zom'})), encoding='utf-8')
    with pytest.raises(ProfileError) as caught:
        read_profile(path)
    assert caught.value.file == str(path)
    assert str(caught.value).startswith(f'{path}: availableChannels.Dimmer.capability.type: ')
