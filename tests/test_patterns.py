"""The pattern library (pylzr.fixtures.patterns): entries, matching a request
by category and scales, editing, the binding file's "patterns" section, and
the pattern attribute's mapping."""

import pytest

from pylzr.fixtures import BindingError, Kind, PatternEntry, PatternLibrary, PatternMapping, PatternRequest
from pylzr.fixtures.jsonio import ObjectReader
from pylzr.fixtures.patterns import UNRATED

CHANNELS = ('Pattern Group', 'Pattern Selection')
NONE = {'Pattern Selection': 0}


def entry(name, group, number, category='tunnel', **scales):
    return PatternEntry(name, {'Pattern Group': group, 'Pattern Selection': number}, category, scales)


def library(*entries):
    return PatternLibrary(CHANNELS, NONE, entries)


def gruolin_library():
    return library(
        entry('calm tunnel', 0, 5, energy=0.2, sharpness=0.4),
        entry('wild tunnel', 0, 10, energy=1.0, sharpness=1.0, complexity=0.8),
        entry('middle tunnel', 0, 15),                                    # not rated: counts as level 3
        entry('star', 16, 5, category='star', energy=0.8),
    )


# ── Entries ──────────────────────────────────────────────────────────────

def test_an_entry_holds_its_values_and_tags():
    e = entry('  Big   Tunnel ', 64, 15, energy=0.8)
    assert e.name == 'Big Tunnel'                                         # spaces tidied, case kept
    assert dict(e.values) == {'Pattern Group': 64, 'Pattern Selection': 15}
    assert (e.category, dict(e.scales)) == ('tunnel', {'energy': 0.8})
    assert e.rating('energy') == 0.8 and e.rating('sharpness') == UNRATED == 0.6


def test_entries_are_read_only():
    e = entry('t', 0, 5, energy=0.2)
    with pytest.raises(TypeError):
        e.values['Pattern Group'] = 3                                     # type: ignore[index]
    with pytest.raises(TypeError):
        e.scales['energy'] = 1                                            # type: ignore[index]


@pytest.mark.parametrize('kwargs, where, message', [
    (dict(name=''), 'name', 'needs a name'),
    (dict(name='x' * 33), 'name', 'needs a name of 1–32'),
    (dict(values={}), 'values', 'at least one channel value'),
    (dict(values={'Pattern Group': 256}), 'values.Pattern Group', 'must be a DMX value'),
    (dict(values={'Pattern Group': True}), 'values.Pattern Group', 'must be a DMX value'),
    (dict(category='Tunnel!'), 'category', 'is not a category name'),
    (dict(scales={'Energy': 0.4}), 'scales.Energy', 'is not a scale name'),
    (dict(scales={'energy': 0}), 'scales.energy', 'above 0 and at most 1'),
    (dict(scales={'energy': 1.2}), 'scales.energy', 'above 0 and at most 1'),
])
def test_bad_entries(kwargs, where, message):
    args = dict(name='tunnel', values={'Pattern Group': 0, 'Pattern Selection': 5}, category='tunnel') | kwargs
    with pytest.raises(BindingError, match=message) as info:
        PatternEntry(**args)
    assert info.value.where == where


# ── The library ──────────────────────────────────────────────────────────

def test_every_entry_sets_every_pattern_channel():
    with pytest.raises(BindingError, match='sets no value for "Pattern Group"') as info:
        library(PatternEntry('t', {'Pattern Selection': 5}, 'tunnel'))
    assert info.value.where == 'library[0].values'
    with pytest.raises(BindingError, match='"Zoom" is not one of the pattern channels') as info:
        library(PatternEntry('t', {'Pattern Group': 0, 'Pattern Selection': 5, 'Zoom': 3}, 'tunnel'))
    assert info.value.where == 'library[0].values.Zoom'


@pytest.mark.parametrize('entries, where, message', [
    ((entry('a', 0, 5), entry('A', 0, 10)), 'library[1].name', 'the name "A" is already used'),
    ((entry('a', 0, 5), entry('b', 0, 5)), 'library[1].values', 'the same pattern as "a"'),
    ((entry('a', 7, 0),), 'library[0].values', 'mean "no pattern"'),
])
def test_library_rules(entries, where, message):
    with pytest.raises(BindingError, match=message) as info:
        library(*entries)
    assert info.value.where == where


@pytest.mark.parametrize('channels, none, where, message', [
    ((), NONE, 'channels', 'needs the channel names'),
    (('Pattern Group', 'Pattern Group'), {'Pattern Group': 0}, 'channels', 'lists a channel twice'),
    (CHANNELS, {}, 'none', 'at least one channel value'),
    (CHANNELS, {'Zoom': 0}, 'none.Zoom', 'not one of the pattern channels'),
])
def test_bad_library_shape(channels, none, where, message):
    with pytest.raises(BindingError, match=message) as info:
        PatternLibrary(channels, none)
    assert info.value.where == where


def test_lookups():
    lib = gruolin_library()
    assert lib.entry('WILD  tunnel').name == 'wild tunnel'
    assert lib.entry('nothing') is None
    assert lib.find({'Pattern Group': 16, 'Pattern Selection': 5}).name == 'star'
    assert lib.find({'Pattern Group': 16, 'Pattern Selection': 6}) is None
    assert [e.name for e in lib.in_category('tunnel')] == ['calm tunnel', 'wild tunnel', 'middle tunnel']


# ── Matching ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize('request_, expected', [
    (PatternRequest.entry('Star'), 'star'),
    (PatternRequest.entry('nothing'), None),
    (PatternRequest.of('tunnel'), 'calm tunnel'),                            # all tie: the first
    (PatternRequest.of('tunnel', energy=1.0), 'wild tunnel'),
    (PatternRequest.of('tunnel', energy=0.2), 'calm tunnel'),
    (PatternRequest.of('tunnel', energy=0.6), 'middle tunnel'),              # unrated = the middle
    (PatternRequest.of('tunnel', energy=0.2, sharpness=1.0), 'middle tunnel'),  # .16+.16 beats 0+.36 and .64+0
    (PatternRequest.of('tunnel', energy=0.2, sharpness=0.6), 'calm tunnel'),    # 0+.04 beats .16+0 and .64+.16
    (PatternRequest.of('tunnel', complexity=0.8), 'wild tunnel'),
    (PatternRequest.of('tunnel', mood=0.2), 'calm tunnel'),                  # a scale nobody rates: all tie
    (PatternRequest.of('star', energy=0.2), 'star'),                         # the only one in its category
    (PatternRequest.of('circle'), None),
])
def test_match(request_, expected):
    found = gruolin_library().match(request_)
    assert (found.name if found else None) == expected


def test_equal_distances_tie_exactly_and_go_to_the_earlier_entry():
    """0.8 − 0.6 and 1.0 − 0.8 differ in floating point; matching compares whole thousandths."""
    lib = library(entry('low', 0, 5, energy=0.6), entry('high', 0, 10, energy=1.0))
    assert lib.match(PatternRequest.of('tunnel', energy=0.8)).name == 'low'
    lib = library(entry('high', 0, 10, energy=1.0), entry('low', 0, 5, energy=0.6))
    assert lib.match(PatternRequest.of('tunnel', energy=0.8)).name == 'high'


def test_unrated_counts_as_level_three():
    lib = library(entry('rated 2', 0, 5, energy=0.4), entry('unrated', 0, 10))
    assert lib.match(PatternRequest.of('tunnel', energy=0.7)).name == 'unrated'
    assert lib.match(PatternRequest.of('tunnel', energy=0.45)).name == 'rated 2'


# ── Editing ──────────────────────────────────────────────────────────────

def test_adding_replacing_and_removing_make_new_libraries():
    lib = gruolin_library()
    added = lib.with_entry(entry('circle 1', 32, 5, category='circle'))
    assert [e.name for e in added.entries][-1] == 'circle 1' and len(lib.entries) == 4
    replaced = added.with_entry(entry('Calm Tunnel', 0, 5, energy=0.4), replacing='calm tunnel')
    assert replaced.entries[0].name == 'Calm Tunnel' and replaced.entries[0].rating('energy') == 0.4
    removed = replaced.without('star')
    assert [e.name for e in removed.entries] == ['Calm Tunnel', 'wild tunnel', 'middle tunnel', 'circle 1']


def test_edits_keep_the_rules():
    lib = gruolin_library()
    with pytest.raises(BindingError, match='already used'):
        lib.with_entry(entry('star', 99, 5))
    with pytest.raises(BindingError, match='the same pattern as "star"'):
        lib.with_entry(entry('star 2', 16, 5))
    with pytest.raises(KeyError, match='no pattern called "nope"'):
        lib.with_entry(entry('x', 99, 5), replacing='nope')
    with pytest.raises(KeyError, match='no pattern called "nope"'):
        lib.without('nope')


# ── The file section ─────────────────────────────────────────────────────

SECTION = {
    'channels': ['Pattern Group', 'Pattern Selection'],
    'none': {'Pattern Selection': 0},
    'library': [
        {'name': 'calm tunnel', 'values': {'Pattern Group': 0, 'Pattern Selection': 5}, 'category': 'tunnel',
         'scales': {'energy': 0.2, 'sharpness': 0.4}},
        {'name': 'middle tunnel', 'values': {'Pattern Group': 0, 'Pattern Selection': 15}, 'category': 'tunnel'},
    ],
}


def read(data):
    return PatternLibrary.from_json(ObjectReader(data, 'patterns', BindingError))


def test_section_round_trip():
    lib = read(SECTION)
    assert lib.to_json() == SECTION
    assert lib.entries[1].scales == {}


def test_library_list_is_optional_when_reading():
    assert read({'channels': ['Pattern Selection'], 'none': {'Pattern Selection': 0}}).entries == ()


@pytest.mark.parametrize('change, where, message', [
    (lambda d: d['library'][0].update(name=5), 'patterns.library[0].name', 'must be text'),
    (lambda d: d['library'][0].update(colour='red'), 'patterns.library[0]', 'unknown key "colour"'),
    (lambda d: d['library'][0]['values'].update({'Pattern Group': 'x'}), 'patterns.library[0].values.Pattern Group',
     'must be a whole number'),
    (lambda d: d['library'][1]['values'].update({'Pattern Selection': 5}), 'patterns.library[1].values',
     'the same pattern as "calm tunnel"'),
    (lambda d: d['library'][0]['scales'].update(energy='high'), 'patterns.library[0].scales.energy',
     'must be a number'),
    (lambda d: d['library'][0].update(category='Tunnel'), 'patterns.library[0].category', 'not a category name'),
    (lambda d: d.update(channels=['Pattern Group', 3]), 'patterns.channels[1]', 'must be text'),
    (lambda d: d.update(nope=1), 'patterns', 'unknown key "nope"'),
    (lambda d: d.pop('none'), 'patterns', '"none" is missing'),
])
def test_section_errors_name_their_place(change, where, message):
    import copy
    data = copy.deepcopy(SECTION)
    change(data)
    with pytest.raises(BindingError, match=message) as info:
        read(data)
    assert info.value.where == where


# ── The pattern attribute's mapping ──────────────────────────────────────

def test_pattern_mapping_sends_the_matched_entry():
    mapping = PatternMapping(gruolin_library())
    assert mapping.kinds == {'pattern': Kind.PATTERN} and mapping.channels == CHANNELS
    assert mapping.render({'pattern': PatternRequest.of('tunnel', energy=1.0)}) == {
        'Pattern Group': 0, 'Pattern Selection': 10}
    assert mapping.chosen({'pattern': PatternRequest.of('star')}).name == 'star'


def test_unset_or_unmatched_patterns_send_no_pattern():
    mapping = PatternMapping(gruolin_library())
    assert mapping.active({}) and mapping.render({}) == {'Pattern Selection': 0}
    assert mapping.render({'pattern': PatternRequest.of('circle')}) == {'Pattern Selection': 0}
    assert mapping.chosen({}) is None


def test_pattern_mapping_outputs_and_off_values():
    mapping = PatternMapping(gruolin_library())
    assert mapping.outputs() == {'Pattern Selection': frozenset({0, 5, 10, 15}), 'Pattern Group': frozenset({0, 16})}
    assert mapping.off_values() == {'Pattern Selection': frozenset({0})}
    assert PatternMapping(library()).outputs() == {'Pattern Selection': frozenset({0})}
