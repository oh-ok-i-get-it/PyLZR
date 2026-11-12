"""The patch (pylzr.fixtures.patch): patch.json, the naming and address
rules, problems that need footprints, the next free address, and rendering
several fixtures through a Rig."""

import copy

import pytest
from shipped import GRUOLIN, renderer

from pylzr.fixtures import Patch, PatchEntry, PatchError, PatchProblem, Rig, load_patch, read_patch, write_patch
from pylzr.fixtures.jsonio import dumps

PATCH = {'version': 1, 'fixtures': [
    {'name': 'Laser L', 'type': GRUOLIN, 'address': 1},
    {'name': 'Laser R', 'type': GRUOLIN, 'address': 37},
]}
FOOTPRINTS = {GRUOLIN: 36, 'small': 4}


def two_gruolins():
    return load_patch(copy.deepcopy(PATCH))


def patch(*entries):
    return Patch(tuple(PatchEntry(*e) for e in entries))


# ── Entries and the file ─────────────────────────────────────────────────

def test_load_and_round_trip(tmp_path):
    p = two_gruolins()
    assert p.names == ('Laser L', 'Laser R') and p.entries[1] == PatchEntry('Laser R', GRUOLIN, 37)
    assert p.to_json() == PATCH
    path = tmp_path / 'fixtures' / 'patch.json'
    write_patch(path, p)
    assert path.read_bytes() == dumps(PATCH).encode('utf-8') and read_patch(path) == p


def test_an_empty_patch():
    assert load_patch({'version': 1, 'fixtures': []}) == Patch()


@pytest.mark.parametrize('args, where, message', [
    (('', GRUOLIN, 1), 'name', 'needs a name of 1–32'),
    (('x' * 33, GRUOLIN, 1), 'name', 'needs a name of 1–32'),
    (('Laser', ' ', 1), 'type', 'needs a fixture type'),
    (('Laser', GRUOLIN, 0), 'address', 'from 1 to 512'),
    (('Laser', GRUOLIN, 513), 'address', 'from 1 to 512'),
    (('Laser', GRUOLIN, True), 'address', 'from 1 to 512'),
])
def test_bad_entries(args, where, message):
    with pytest.raises(PatchError, match=message) as info:
        PatchEntry(*args)
    assert info.value.where == where


def test_names_are_tidied_and_unique_ignoring_case():
    assert PatchEntry('  Laser   L ', GRUOLIN, 1).name == 'Laser L'
    with pytest.raises(PatchError, match='"laser l" is already used') as info:
        patch(('Laser L', GRUOLIN, 1), ('laser l', GRUOLIN, 37))
    assert info.value.where == 'fixtures[1].name'


@pytest.mark.parametrize('change, where, message', [
    (lambda d: d.update(version=9), '', 'newer PyLZR'),
    (lambda d: d['fixtures'][0].pop('type'), 'fixtures[0]', '"type" is missing'),
    (lambda d: d['fixtures'][0].update(adress=3), 'fixtures[0]', 'unknown key "adress"'),
    (lambda d: d['fixtures'][1].update(address='37'), 'fixtures[1].address', 'must be a whole number'),
    (lambda d: d['fixtures'][1].update(address=600), 'fixtures[1].address', 'from 1 to 512'),
    (lambda d: d['fixtures'][1].update(name='LASER L'), 'fixtures[1].name', 'already used'),
])
def test_file_errors_name_their_place(change, where, message):
    data = copy.deepcopy(PATCH)
    change(data)
    with pytest.raises(PatchError, match=message) as info:
        load_patch(data)
    assert info.value.where == where


def test_file_errors_name_the_file(tmp_path):
    path = tmp_path / 'patch.json'
    path.write_text('{"version": 1}', encoding='utf-8')
    with pytest.raises(PatchError, match='patch.json: "fixtures" is missing'):
        read_patch(path)


def test_editing():
    p = two_gruolins()
    added = p.with_fixture(PatchEntry('Small', 'small', 73))
    assert added.names == ('Laser L', 'Laser R', 'Small') and p.names == ('Laser L', 'Laser R')
    moved = added.replaced('laser r', PatchEntry('Laser R', GRUOLIN, 100))
    assert moved.entry('Laser R').address == 100 and moved.names == ('Laser L', 'Laser R', 'Small')
    assert moved.without('Laser L').names == ('Laser R', 'Small')
    with pytest.raises(KeyError, match='no fixture called "nope"'):
        p.without('nope')
    with pytest.raises(PatchError, match='already used'):
        p.with_fixture(PatchEntry('LASER R', GRUOLIN, 200))


# ── Problems and free addresses ──────────────────────────────────────────

def test_two_gruolins_side_by_side_are_fine():
    assert two_gruolins().problems(FOOTPRINTS) == ()


@pytest.mark.parametrize('entries, expected', [
    ([('A', GRUOLIN, 1), ('B', GRUOLIN, 36)], ['B: channels 36–71 overlap A (1–36)']),
    ([('A', GRUOLIN, 1), ('B', GRUOLIN, 37)], []),                                     # touching is fine
    ([('A', GRUOLIN, 40), ('B', 'small', 37)], ['B: channels 37–40 overlap A (40–75)']),
    ([('A', GRUOLIN, 40), ('B', 'small', 36)], []),
    ([('A', GRUOLIN, 477)], []),                                                       # ends at 512 exactly
    ([('A', GRUOLIN, 478)], ['A: needs channels 478–513, but a universe ends at 512']),
    ([('A', 'gone/laser', 1)], ['A: its type "gone/laser" isn\'t available']),
])
def test_problems(entries, expected):
    assert [str(p) for p in patch(*entries).problems(FOOTPRINTS)] == expected


def test_only_the_later_fixture_of_an_overlap_is_flagged():
    problems = patch(('A', GRUOLIN, 1), ('B', GRUOLIN, 20), ('C', GRUOLIN, 37)).problems(FOOTPRINTS)
    assert problems == (PatchProblem('B', 'channels 20–55 overlap A (1–36)'),)        # C is fine: B isn't placed


@pytest.mark.parametrize('entries, footprint, expected', [
    ([], 36, 1),
    ([('A', GRUOLIN, 1)], 36, 37),
    ([('A', GRUOLIN, 1), ('B', GRUOLIN, 37)], 36, 73),
    ([('A', GRUOLIN, 1), ('B', GRUOLIN, 60)], 36, 96),                      # 37–59 is too small a gap
    ([('A', GRUOLIN, 1), ('B', GRUOLIN, 60)], 23, 37),                      # … but fits 23 exactly
    ([('A', GRUOLIN, 10)], 9, 1),
    ([('A', GRUOLIN, 10)], 10, 46),
    ([('A', 'gone/laser', 1)], 4, 2),                                       # an unavailable type holds one channel
    ([('A', GRUOLIN, 1), ('B', GRUOLIN, 37)], 440, 73),                     # up to 512 exactly
    ([('A', GRUOLIN, 1), ('B', GRUOLIN, 37)], 441, None),
    ([('A', GRUOLIN, 1)], 512, None),
])
def test_next_free_address(entries, footprint, expected):
    assert patch(*entries).next_free_address(footprint, FOOTPRINTS) == expected


@pytest.mark.parametrize('names, expected', [
    ([], 'Laser 1'),
    (['Laser 1'], 'Laser 2'),
    (['Laser 2'], 'Laser 1'),                                               # the lowest free number
    (['Laser 1', 'Laser 2', 'Laser 4'], 'Laser 3'),
    (['laser 1'], 'Laser 2'),                                               # ignoring case
    (['Laser L', 'Laser R'], 'Laser 1'),
])
def test_next_name(names, expected):
    assert patch(*((name, GRUOLIN, 1 + 36 * i) for i, name in enumerate(names))).next_name() == expected
    assert Patch().next_name('Beam') == 'Beam 1'


# ── Rendering through a rig ──────────────────────────────────────────────

def rig(p=None):
    return Rig(p or two_gruolins(), {GRUOLIN: renderer()})


def test_render_one_fixture_for_the_tester():
    start, result = rig().render_fixture('laser r', {'power': 'on', 'size': 0.0})
    assert start == 37 and len(result.values) == 36
    assert result.values[0] == 255 and result.values[4] == 255


def test_two_gruolins_dont_touch_each_other():
    channels = rig().render({'Laser L': {'power': 'on', 'color': 'red'}, 'Laser R': {'size@b': 0.0}})
    assert sorted(channels) == list(range(1, 73))
    assert (channels[1], channels[8], channels[37], channels[44]) == (255, 8, 0, 0)
    assert channels[36 + 22] == 255 and channels[22] == 0                 # Laser R's layer b only


def test_a_fixture_with_a_problem_is_kept_listed_but_not_rendered():
    p = patch(('A', GRUOLIN, 1), ('B', GRUOLIN, 20), ('Gone', 'gone/laser', 100))
    r = rig(p)
    assert r.usable == ('A',) and [p.name for p in r.problems] == ['B', 'Gone']
    assert r.render({'A': {'power': 'on'}, 'B': {'power': 'on'}}) == {
        ch: (255 if ch == 1 else value) for ch, value in enumerate(renderer().defaults, 1)}
    with pytest.raises(KeyError, match='B: channels 20–55 overlap A'):
        r.render_fixture('B', {})
    with pytest.raises(KeyError, match='no fixture called "Nope"'):
        r.render({'Nope': {}})
    assert r.renderer('a') is renderer()
