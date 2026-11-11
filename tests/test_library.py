"""The fixture library (pylzr.fixtures.library): shipped files plus your
folder, yours overriding shipped, problems instead of crashes, and saving
only ever to your folder. Each test works in its own temporary folders."""

import json
from dataclasses import replace

import pytest
from shipped import GRUOLIN, resource

from pylzr.fixtures import (
    BindingError, FixtureLibrary, Patch, PatchEntry, PatternEntry, Problem, Vocabulary, load_binding,
)
from pylzr.fixtures.jsonio import dumps
from pylzr.fixtures.vocabulary import Scale

PROFILE = 'gruolin/rgb-fullcolor-beam-effect-light'


def shipped_json(kind, key):
    return json.loads(resource(kind, *f'{key}.json'.split('/')).read_text(encoding='utf-8'))


def put(folder, relative, data):
    """Write `data` (JSON, or text as is) at folder/relative."""
    path = folder / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else dumps(data), encoding='utf-8')
    return path


@pytest.fixture
def yours(tmp_path):
    return tmp_path / 'PyLZR' / 'fixtures'


@pytest.fixture
def fake_shipped(tmp_path):
    """A copy of the shipped files that a test may change."""
    folder = tmp_path / 'shipped'
    put(folder, f'profiles/{PROFILE}.json', shipped_json('profiles', PROFILE))
    put(folder, f'bindings/{GRUOLIN}.json', shipped_json('bindings', GRUOLIN))
    return folder


def renamed_gruolin(name):
    return shipped_json('bindings', GRUOLIN) | {'name': name}


# ── Loading ──────────────────────────────────────────────────────────────

def test_shipped_files_alone():
    library = FixtureLibrary(None)
    assert library.types() == [(GRUOLIN, 'Gruolin RGB Beam (36ch)')]
    assert list(library.profiles) == [PROFILE] and library.source(GRUOLIN) == 'shipped'
    assert library.problems == () and library.patch == Patch() and library.vocabulary == Vocabulary()


def test_a_missing_folder_is_an_empty_one(yours):
    library = FixtureLibrary(yours)
    assert library.types() == FixtureLibrary(None).types() and library.problems == ()
    assert not yours.exists()                                              # loading never creates it


def test_your_binding_overrides_the_shipped_one(yours):
    put(yours, f'bindings/{GRUOLIN}.json', renamed_gruolin('My Gruolin'))
    library = FixtureLibrary(yours)
    assert library.types() == [(GRUOLIN, 'My Gruolin')] and library.source(GRUOLIN) == 'yours'


def test_your_own_fixture_types_and_profiles(yours):
    put(yours, 'bindings/me/second.json', renamed_gruolin('Second') | {'mode': '36ch'})
    put(yours, 'profiles/me/copy.json', shipped_json('profiles', PROFILE))
    put(yours, 'bindings/me/on-copy.json', renamed_gruolin('On my copy') | {'profile': 'me/copy'})
    library = FixtureLibrary(yours)
    assert [name for _, name in library.types()] == ['Gruolin RGB Beam (36ch)', 'On my copy', 'Second']
    assert library.renderers['me/on-copy'].resolved.profile.key == 'me/copy'
    assert library.renderers['me/second'].key == 'me/second'


def test_a_broken_file_of_yours_falls_back_to_the_shipped_one(yours):
    put(yours, f'bindings/{GRUOLIN}.json', '{"version": 1, "name": ')
    library = FixtureLibrary(yours)
    assert library.source(GRUOLIN) == 'shipped'
    [problem] = library.problems
    assert problem.file == f'bindings/{GRUOLIN}.json'
    assert 'is not valid JSON' in problem.message and problem.message.endswith('(using the shipped one instead)')


def test_a_binding_that_doesnt_fit_its_profile_falls_back_too(yours):
    data = renamed_gruolin('Mine')
    data['mappings'][1]['attribute'] = 'sise'
    put(yours, f'bindings/{GRUOLIN}.json', data)
    library = FixtureLibrary(yours)
    assert library.types() == [(GRUOLIN, 'Gruolin RGB Beam (36ch)')]
    assert str(library.problems[0]) == (f'bindings/{GRUOLIN}.json: mappings[1]: unknown attribute "sise" '
                                        '(did you mean "size"?) (using the shipped one instead)')


def test_a_broken_file_never_blocks_the_others(yours):
    put(yours, 'bindings/me/broken.json', '[]')
    put(yours, 'bindings/me/no-profile.json', renamed_gruolin('Orphan') | {'profile': 'me/gone'})
    put(yours, 'profiles/me/bad.json', '{"name": "Bad"}')
    put(yours, 'bindings/me/fine.json', renamed_gruolin('Fine'))
    library = FixtureLibrary(yours)
    assert sorted(library.renderers) == [GRUOLIN, 'me/fine']
    assert [str(p) for p in library.problems] == [
        'profiles/me/bad.json: "categories" is missing',
        'bindings/me/broken.json: must be an object, not a list',
        'bindings/me/no-profile.json: profile: its profile "me/gone" isn\'t available',
    ]


def test_a_broken_shipped_file_is_reported_as_shipped(fake_shipped):
    put(fake_shipped, f'bindings/{GRUOLIN}.json', '{}')
    library = FixtureLibrary(None, fake_shipped)
    assert library.renderers == {} and library.problems == (
        Problem(f'bindings/{GRUOLIN}.json (shipped)', '"version" is missing'),)


def test_your_profile_overrides_and_falls_back(yours, fake_shipped):
    profile = shipped_json('profiles', PROFILE)
    put(yours, f'profiles/{PROFILE}.json', profile | {'shortName': 'Mine'})
    assert FixtureLibrary(yours, fake_shipped).profiles[PROFILE].short_name == 'Mine'
    put(yours, f'profiles/{PROFILE}.json', profile | {'shortName': 5})
    library = FixtureLibrary(yours, fake_shipped)
    assert library.profiles[PROFILE].short_name == 'Gruolin RGB Beam' and len(library.problems) == 1


def test_hidden_and_set_aside_files_are_skipped(yours):
    put(yours, 'bindings/me/.draft.json', '{')
    put(yours, 'bindings/me/old.unreadable.json', '{')
    put(yours, 'bindings/me/notes.txt', 'hello')
    assert FixtureLibrary(yours).problems == ()


def test_reload_sees_new_files(yours):
    library = FixtureLibrary(yours)
    put(yours, 'bindings/me/new.json', renamed_gruolin('New'))
    library.reload()
    assert 'me/new' in library.renderers


# ── Your patch and vocabulary ────────────────────────────────────────────

def test_patch_and_vocabulary_are_read_from_your_folder(yours):
    put(yours, 'patch.json', {'version': 1, 'fixtures': [{'name': 'L', 'type': GRUOLIN, 'address': 1}]})
    put(yours, 'vocabulary.json', {'version': 1, 'categories': ['spiral'], 'scales': []})
    library = FixtureLibrary(yours)
    assert library.patch.names == ('L',) and library.vocabulary.own_categories == ('spiral',)
    assert library.rig().usable == ('L',)


def test_unreadable_patch_starts_empty_and_is_kept_when_saving(yours):
    broken = '{"version": 1, "fixtures": [{"name": "L"}]}'
    put(yours, 'patch.json', broken)
    library = FixtureLibrary(yours)
    assert library.patch == Patch()
    assert str(library.problems[0]) == 'patch.json: fixtures[0]: "type" is missing (starting without it)'
    library.save_patch(Patch((PatchEntry('R', GRUOLIN, 37),)))
    assert (yours / 'patch.unreadable.json').read_text(encoding='utf-8') == broken
    assert FixtureLibrary(yours).patch.names == ('R',)
    library.save_patch(Patch())                                              # now readable: just saved over
    assert sorted(p.name for p in yours.iterdir()) == ['patch.json', 'patch.unreadable.json']


def test_set_aside_files_are_numbered(yours):
    put(yours, 'patch.unreadable.json', '{"older": 1}')
    put(yours, 'patch.json', 'nonsense')
    FixtureLibrary(yours).save_patch(Patch())
    assert (yours / 'patch.unreadable-2.json').read_text(encoding='utf-8') == 'nonsense'
    assert (yours / 'patch.unreadable.json').read_text(encoding='utf-8') == '{"older": 1}'


def test_saving_the_vocabulary(yours):
    library = FixtureLibrary(yours)
    words = Vocabulary().with_category('Spiral').with_scale(Scale('speed', 'slow', 'fast'))
    library.save_vocabulary(words)
    assert library.vocabulary == words and FixtureLibrary(yours).vocabulary == words


def test_a_patch_with_a_missing_type_is_kept_and_flagged(yours):
    put(yours, 'patch.json', {'version': 1, 'fixtures': [{'name': 'L', 'type': GRUOLIN, 'address': 1},
                                                         {'name': 'Old', 'type': 'me/deleted', 'address': 37}]})
    rig = FixtureLibrary(yours).rig()
    assert rig.patch.names == ('L', 'Old') and rig.usable == ('L',)
    assert [str(p) for p in rig.problems] == ['Old: its type "me/deleted" isn\'t available']


# ── Saving bindings: copy on edit ────────────────────────────────────────

def tagged(library):
    binding = library.renderers[GRUOLIN].resolved.binding
    entry = PatternEntry('tunnel', {'Pattern Group': 64, 'Pattern Selection': 15}, 'tunnel', {'energy': 0.8})
    return binding.with_patterns(binding.patterns.with_entry(entry))


def test_tagging_a_shipped_binding_saves_your_copy(yours, fake_shipped):
    shipped_file = fake_shipped / f'bindings/{GRUOLIN}.json'
    before = shipped_file.read_bytes()
    library = FixtureLibrary(yours, fake_shipped)
    renderer = library.save_binding(tagged(library))
    assert shipped_file.read_bytes() == before                                 # never touched
    assert (yours / f'bindings/{GRUOLIN}.json').is_file()
    assert library.source(GRUOLIN) == 'yours' and library.renderers[GRUOLIN] is renderer
    reloaded = FixtureLibrary(yours, fake_shipped)
    assert reloaded.source(GRUOLIN) == 'yours'
    assert reloaded.renderers[GRUOLIN].resolved.binding.patterns.entry('tunnel').rating('energy') == 0.8


def test_a_binding_that_doesnt_fit_is_not_saved(yours):
    library = FixtureLibrary(yours)
    binding = load_binding(renamed_gruolin('x') | {'mode': '16ch'}, GRUOLIN)
    with pytest.raises(BindingError):
        library.save_binding(binding)
    assert not yours.exists() and library.source(GRUOLIN) == 'shipped'


def test_saving_over_your_broken_binding_keeps_it(yours):
    put(yours, f'bindings/{GRUOLIN}.json', '{"version": 1, typo}')
    library = FixtureLibrary(yours)
    library.save_binding(tagged(library))
    assert (yours / 'bindings/gruolin/rgb-beam-36ch.unreadable.json').read_text(encoding='utf-8') == \
        '{"version": 1, typo}'
    assert FixtureLibrary(yours).problems == ()


def test_bindings_need_a_key_to_be_saved(yours):
    library = FixtureLibrary(yours)
    with pytest.raises(ValueError, match='needs its key'):
        library.save_binding(replace(tagged(library), key=''))


def test_without_a_folder_nothing_can_be_saved():
    library = FixtureLibrary(None)
    with pytest.raises(RuntimeError, match='no fixtures folder'):
        library.save_patch(Patch())


def test_the_real_shipped_files_load_cleanly():
    """Guards the package data itself: no problems, every binding usable."""
    library = FixtureLibrary(None)
    assert library.problems == () and set(library.renderers) == {GRUOLIN}
