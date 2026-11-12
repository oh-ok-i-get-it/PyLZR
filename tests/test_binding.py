"""Bindings (pylzr.fixtures.binding): the file format, saving, and resolving
against a profile with its safety and layer rules. Uses the made-up profile
in sample_fixture.py; the shipped Gruolin binding has its own tests."""

import copy

import pytest
from sample_fixture import KEY, profile

from pylzr.fixtures import (
    Binding, BindingError, Kind, Linear, LinearSpec, PatternEntry, PatternMapping, PatternRequest, load_binding,
    read_binding, write_binding,
)
from pylzr.fixtures.jsonio import dumps

BINDING = {
    'version': 1,
    'name': 'Sample (15ch)',
    'comment': 'For tests',
    'profile': KEY,
    'mode': '15ch',
    'layers': {'a': 0, 'b': 7},
    'base': {'Strobe': 0},
    'extras': [
        {'name': 'x_wobble', 'kind': 'continuous', 'description': 'Wobble speed'},
        {'name': 'x_master', 'kind': 'option', 'options': ['dim', 'bright'], 'layered': False},
    ],
    'mappings': [
        {'type': 'options', 'attribute': 'power', 'values': {'off': {'Power': 0}, 'on': {'Power': 255}}},
        {'type': 'options', 'attribute': 'x_master', 'values': {'dim': {'Power': 10}, 'bright': {'Power': 255}}},
        {'type': 'linear', 'attribute': 'size', 'channel': 'Size', 'invert': True},
        {'type': 'bipolar', 'attribute': 'pos_x', 'channel': 'Position', 'centre': 128, 'limit': 0.5},
        {'type': 'options', 'attribute': 'color', 'values': {'white': {'Colour': 0}, 'red': {'Colour': 8}}},
        {'type': 'linear', 'attribute': 'strobe', 'channel': 'Strobe', 'segment': 10, 'zero': 0},
        {'type': 'linear', 'attribute': 'x_wobble', 'channel': 'Gap', 'segment': 0, 'zero': 'release'},
    ],
    'patterns': {
        'channels': ['Pattern'],
        'none': {'Pattern': 0},
        'library': [{'name': 'tunnel', 'values': {'Pattern': 5}, 'category': 'tunnel', 'scales': {'energy': 0.8}}],
    },
}


def data(change=None):
    d = copy.deepcopy(BINDING)
    if change:
        change(d)
    return d


def resolve(change=None):
    return load_binding(data(change)).resolve(profile())


# ── Loading and saving ───────────────────────────────────────────────────

def test_load():
    b = load_binding(data(), 'test/sample-15ch')
    assert (b.key, b.name, b.comment, b.profile, b.mode) == ('test/sample-15ch', 'Sample (15ch)', 'For tests', KEY,
                                                             '15ch')
    assert dict(b.layers) == {'a': 0, 'b': 7} and dict(b.base) == {'Strobe': 0}
    assert [e.name for e in b.extras] == ['x_wobble', 'x_master']
    assert b.extras[1].layered is False and b.extras[1].options == ('dim', 'bright')
    assert isinstance(b.mappings[2], LinearSpec) and b.patterns.entries[0].name == 'tunnel'


def test_to_json_is_the_file():
    assert load_binding(data()).to_json() == BINDING


def test_minimal_binding_and_its_defaults():
    minimal = {'version': 1, 'name': 'Tiny', 'profile': KEY, 'mode': '3ch',
               'mappings': [{'type': 'linear', 'attribute': 'size', 'channel': 'Size'}]}
    b = load_binding(minimal)
    assert dict(b.layers) == {'a': 0} and dict(b.base) == {} and b.extras == () and b.patterns is None
    assert b.to_json() == minimal
    assert load_binding({**minimal, 'layers': {'a': 0}, 'base': {}, 'extras': [], 'comment': ''}).to_json() == minimal


def test_save_and_read_back_gives_the_same_bytes(tmp_path):
    path = tmp_path / 'bindings' / 'test' / 'sample-15ch.json'
    write_binding(path, load_binding(data()))
    text = path.read_bytes()
    assert text == dumps(BINDING).encode('utf-8')
    again = read_binding(path, 'test/sample-15ch')
    write_binding(path, again)
    assert path.read_bytes() == text and again == load_binding(data(), 'test/sample-15ch')


def test_file_errors_name_the_file(tmp_path):
    path = tmp_path / 'broken.json'
    path.write_text('{"version": 1, "name": "x"}', encoding='utf-8')
    with pytest.raises(BindingError, match='broken.json: "profile" is missing'):
        read_binding(path)


def test_tagging_patterns_makes_a_new_binding():
    b = load_binding(data())
    tagged = b.with_patterns(b.patterns.with_entry(PatternEntry('star', {'Pattern': 9}, 'star')))
    assert [e.name for e in tagged.patterns.entries] == ['tunnel', 'star']
    assert [e.name for e in b.patterns.entries] == ['tunnel']


@pytest.mark.parametrize('change, where, message', [
    (lambda d: d.update(version=2), '', 'made by a newer PyLZR'),
    (lambda d: d.pop('version'), '', '"version" is missing'),
    (lambda d: d.update(mappinsg=[]), '', 'unknown key "mappinsg" \\(did you mean "mappings"\\?\\)'),
    (lambda d: d.update(name='  '), 'name', 'must be some text'),
    (lambda d: d.update(layers={'b': 7}), 'layers', 'must start with "a": 0'),
    (lambda d: d.update(layers={'a': 0, 'c': 7}), 'layers.c', 'named a, b, c, … in order'),
    (lambda d: d.update(layers={'a': 0, 'b': 0}), 'layers.b', 'further on than the one before'),
    (lambda d: d.update(layers={'a': 0, 'b': '7'}), 'layers.b', 'whole number of channels'),
    (lambda d: d.update(base={'Strobe': 300}), 'base.Strobe', 'must be a DMX value'),
    (lambda d: d.update(base={'Strobe': 'x'}), 'base.Strobe', 'must be a whole number'),
    (lambda d: d['extras'][0].update(name='wobble'), 'extras[0]', 'must be named x_<something>'),
    (lambda d: d['extras'][0].update(kind='number'), 'extras[0]', '"number" is not a kind of attribute'),
    (lambda d: d['extras'][1].update(options=[]), 'extras[1]', 'needs its options'),
    (lambda d: d['extras'][0].update(colour=1), 'extras[0]', 'unknown key "colour"'),
    (lambda d: d['extras'].append({'name': 'x_wobble', 'kind': 'continuous'}), 'extras', 'defined twice'),
    (lambda d: d['mappings'][2].update(type='curve'), 'mappings[2].type', 'unknown mapping type'),
    (lambda d: d['patterns']['library'][0].update(category='Tunnel'), 'patterns.library[0].category',
     'not a category name'),
])
def test_load_errors_name_their_place(change, where, message):
    with pytest.raises(BindingError, match=message) as info:
        load_binding(data(change))
    assert info.value.where == where


# ── Resolving ────────────────────────────────────────────────────────────

def test_resolve():
    resolved = resolve()
    assert resolved.mode.short_name == '15ch' and resolved.layers == ('a', 'b')
    assert isinstance(resolved.mappings[0], PatternMapping)                    # patterns first
    assert resolved.mappings[3] == Linear('size', 'Size', 255, 0)
    assert resolved.layered == (True, False, False, True, True, True, True, True)
    assert 'x_wobble' in resolved.attributes and resolved.attributes['x_wobble'].kind == Kind.CONTINUOUS


def test_channels_on_other_layers():
    resolved = resolve()
    assert resolved.channel('Size') == 'Size' and resolved.channel('Size', 'b') == 'Size 2'
    assert resolved.channel('Pattern', 'b') == 'Pattern 2'
    with pytest.raises(KeyError, match='"Pattern 2" has no channel on layer b'):
        resolved.channel('Pattern 2', 'b')


def test_the_pattern_mapping_uses_the_library():
    pattern = resolve().mappings[0]
    assert pattern.render({'pattern': PatternRequest.of('tunnel')}) == {'Pattern': 5}
    assert pattern.render({}) == {'Pattern': 0}


def test_a_binding_without_patterns_or_layers():
    resolved = load_binding({'version': 1, 'name': 'Tiny', 'profile': KEY, 'mode': 'Short',
                             'mappings': [{'type': 'linear', 'attribute': 'size', 'channel': 'Size'}]}
                            ).resolve(profile())
    assert resolved.layers == ('a',) and resolved.layered == (True,)


def test_profile_without_a_key_is_taken_as_given():
    load_binding(data()).resolve(profile(key=''))


def add_mapping(mapping):
    return lambda d: d['mappings'].append(mapping)


@pytest.mark.parametrize('change, where, message', [
    # which profile and mode
    (lambda d: d.update(profile='other/laser'), 'profile', 'is for the profile "other/laser", not "test/sample"'),
    (lambda d: d.update(mode='9ch'), 'mode', 'has no mode "9ch" \\(it has: 15ch, 3ch\\)'),
    # base values
    (lambda d: d.update(base={'Strobe 3': 0}), 'base.Strobe 3', 'the mode has no channel "Strobe 3"'),
    (lambda d: d.update(base={'Gap': 150}), 'base.Gap', '150 on "Gap" isn\'t described by the profile'),
    (lambda d: d.update(base={'Gap': 200}), 'base.Gap', 'Maintenance segment \\(200–255\\)'),
    # attributes
    (add_mapping({'type': 'linear', 'attribute': 'sise', 'channel': 'Size'}), 'mappings[7]',
     'unknown attribute "sise" \\(did you mean "size"\\?\\)'),
    (add_mapping({'type': 'linear', 'attribute': 'pos_x', 'channel': 'Size'}), 'mappings[7]',
     '"pos_x" is a bipolar attribute; a linear mapping needs a continuous one'),
    (add_mapping({'type': 'options', 'attribute': 'color', 'values': {'pink': {'Colour': 8}}}), 'mappings[7]',
     'color has no choice "pink"'),
    (add_mapping({'type': 'selected', 'selector': 'draw_style', 'default': 'line', 'choices': {
        'zigzag': {'type': 'linear', 'attribute': 'scan_speed', 'channel': 'Size'},
        'line': {'type': 'linear', 'attribute': 'scan_speed', 'channel': 'Size'}}}), 'mappings[7]',
     'draw_style has no choice "zigzag"'),
    (add_mapping({'type': 'selected', 'selector': 'power', 'default': 'on', 'choices': {
        'on': {'type': 'linear', 'attribute': 'size', 'channel': 'Size'}}}), 'mappings[7]',
     'mixes attributes of the whole fixture'),
    (lambda d: d['mappings'].pop(6), 'extras[0]', '"x_wobble" isn\'t used by any mapping'),
    # safety
    (add_mapping({'type': 'linear', 'attribute': 'zoom', 'channel': 'Gap', 'segment': 0, 'zero': 200}),
     'mappings[7]', '200 on "Gap" is in a Maintenance segment \\(200–255\\), which PyLZR never sends'),
    (add_mapping({'type': 'options', 'attribute': 'color_effect', 'values': {'jump': {'Strobe': 5}}}),
     'mappings[7]', '5 on "Strobe" is in a NoFunction segment \\(0–9\\); only an off or zero value may be'),
    (add_mapping({'type': 'options', 'attribute': 'color_effect', 'values': {'jump': {'Gap': 150}}}),
     'mappings[7]', '150 on "Gap" isn\'t described'),
    (add_mapping({'type': 'options', 'attribute': 'x_master', 'values': {'dim': {'Gap': 255}}}),
     'mappings[7]', 'Maintenance'),
    # layers
    (add_mapping({'type': 'direction', 'attribute': 'spin_z', 'channel': 'Spin', 'forward': 128, 'reverse': 192}),
     'mappings[7]', '"Spin 2" \\(layer b\\) has different segments from "Spin" \\(check "layers"\\)'),
    (lambda d: (d.pop('patterns'), d.update(layers={'a': 0, 'b': 6})), 'mappings[2]',
     '"Pattern" \\(layer b\\) has different segments from "Size"'),
    (lambda d: d.update(layers={'a': 0, 'b': 9}), 'patterns.none.Pattern',
     '"Pattern" has no channel on layer b: the mode has nothing at channel 17'),
    (add_mapping({'type': 'linear', 'attribute': 'size', 'channel': 'Size 2'}), 'mappings[7]',
     '"Size 2" has no channel on layer b: the mode has nothing at channel 16'),
    # patterns
    (add_mapping({'type': 'options', 'attribute': 'color_effect', 'values': {'jump': {'Pattern': 5}}}),
     'mappings[7]', '"Pattern" is a pattern channel'),
    (lambda d: d['patterns']['library'].append({'name': 'big', 'values': {'Pattern': 150}, 'category': 'star'}),
     'patterns.library[1].values.Pattern', '150 on "Pattern 2" is in a Maintenance segment \\(100–255\\)'),
    (lambda d: d['patterns'].update(channels=['Patern'], none={'Patern': 0}, library=[]), 'patterns.channels[0]',
     'no channel "Patern" \\(did you mean "Pattern"\\?\\)'),
    (lambda d: d['patterns'].update(none={'Pattern': 255}), 'patterns.none.Pattern', 'Maintenance'),
])
def test_resolve_errors_name_their_place(change, where, message):
    with pytest.raises(BindingError, match=message) as info:
        resolve(change)
    assert info.value.where == where


def test_off_values_may_use_no_function_segments():
    """A zero, an off, a choice called off/none, "no pattern" and base values."""
    resolve(add_mapping({'type': 'linear', 'attribute': 'gradient_speed', 'channel': 'Strobe', 'segment': 10,
                         'zero': 5}))
    resolve(add_mapping({'type': 'options', 'attribute': 'color_effect', 'values': {'none': {'Strobe': 5}}}))
    resolve(lambda d: d.update(base={'Strobe': 9, 'Pattern': 0}))


def test_binding_values_are_read_only():
    b = load_binding(data())
    with pytest.raises(TypeError):
        b.layers['b'] = 3                                                     # type: ignore[index]
    with pytest.raises(TypeError):
        b.base['Strobe'] = 3                                                  # type: ignore[index]


def test_bindings_can_be_built_in_code():
    b = Binding('Tiny', KEY, '3ch', (LinearSpec('size', 'Size'),))
    assert b.resolve(profile()).mappings == (Linear('size', 'Size', 0, 255),)
    with pytest.raises(BindingError, match='must be a mapping spec') as info:
        Binding('Tiny', KEY, '3ch', ({'type': 'linear'},))
    assert info.value.where == 'mappings[0]'
