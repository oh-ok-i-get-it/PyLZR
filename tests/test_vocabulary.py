"""Pattern categories and scales (pylzr.fixtures.vocabulary)."""

import pytest

from pylzr.fixtures import (
    LEVELS, STARTER_CATEGORIES, STARTER_SCALES, Scale, Vocabulary, VocabularyError, level_value, value_level,
)
from pylzr.fixtures.jsonio import dumps
from pylzr.fixtures.vocabulary import normalize_name


def test_starter_words_as_agreed():
    assert STARTER_CATEGORIES == ('line', 'tunnel', 'circle', 'wave', 'star', 'grid', 'text', 'abstract',
                                  'animation')
    assert [(s.name, s.low, s.high) for s in STARTER_SCALES] == [
        ('energy', 'calm', 'intense'), ('sharpness', 'smooth', 'sharp'), ('complexity', 'simple', 'complex')]


# ── Levels ───────────────────────────────────────────────────────────────

def test_five_levels_stored_as_fifths():
    assert LEVELS == 5
    assert [level_value(level) for level in range(1, 6)] == [0.2, 0.4, 0.6, 0.8, 1.0]
    assert [value_level(level_value(level)) for level in range(1, 6)] == [1, 2, 3, 4, 5]


@pytest.mark.parametrize('value, level', [(0.01, 1), (0.29, 1), (0.31, 2), (0.65, 3), (0.71, 4), (1, 5)])
def test_values_round_to_the_nearest_level(value, level):
    """A finer scale could come later: any 0–1 value still shows as a level."""
    assert value_level(value) == level


@pytest.mark.parametrize('level', [0, 6, 2.0, True, '3'])
def test_bad_levels(level):
    with pytest.raises(ValueError, match='a level is a whole number from 1 to 5'):
        level_value(level)


@pytest.mark.parametrize('value', [0, -0.2, 1.01, True, None])
def test_bad_stored_values(value):
    with pytest.raises(ValueError, match='a scale value'):
        value_level(value)


# ── Scales ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize('name, low, high, message', [
    ('Density', 'sparse', 'dense', 'not a scale name'),
    ('density', '', 'dense', 'needs low and high labels'),
    ('density', 'sparse', ' ', 'needs low and high labels'),
    ('density', 'sparse', 'x' * 25, 'needs low and high labels'),
    ('d' * 33, 'sparse', 'dense', 'not a scale name'),
])
def test_bad_scales(name, low, high, message):
    with pytest.raises(ValueError, match=message):
        Scale(name, low, high)


# ── Vocabulary (starters + yours) ────────────────────────────────────────

def test_default_is_just_the_starters():
    vocabulary = Vocabulary()
    assert vocabulary.categories == STARTER_CATEGORIES
    assert vocabulary.scales == STARTER_SCALES
    assert vocabulary.scale('energy').high == 'intense'
    assert vocabulary.scale('density') is None
    assert vocabulary.has_category('tunnel') and not vocabulary.has_category('spiral')


def test_your_words_come_after_the_starters():
    density = Scale('density', 'sparse', 'dense')
    vocabulary = Vocabulary().with_category('  Line  Art ').with_scale(density)
    assert vocabulary.categories == STARTER_CATEGORIES + ('line art',)
    assert vocabulary.scales == STARTER_SCALES + (density,)
    assert vocabulary.own_categories == ('line art',) and vocabulary.own_scales == (density,)
    assert vocabulary.has_category('line art')


@pytest.mark.parametrize('make, message', [
    (lambda: Vocabulary(('tunnel',)), 'category "tunnel" is already in the list'),
    (lambda: Vocabulary(('spiral', 'spiral')), 'category "spiral" is already in the list'),
    (lambda: Vocabulary((), (Scale('energy', 'a', 'b'),)), 'scale "energy" is already in the list'),
    (lambda: Vocabulary(('Spiral!',)), 'not a category name'),
    (lambda: Vocabulary().with_category('   '), 'not a category name'),
])
def test_duplicates_and_bad_names_are_refused(make, message):
    with pytest.raises(ValueError, match=message):
        make()


@pytest.mark.parametrize('typed, stored', [('Spiral', 'spiral'), ('  line   art ', 'line art'), ('3D', '3d')])
def test_typed_names_are_normalised(typed, stored):
    assert normalize_name(typed) == stored


# ── vocabulary.json ──────────────────────────────────────────────────────

def test_saved_form_round_trips():
    vocabulary = Vocabulary(('spiral', 'line art'), (Scale('density', 'sparse', 'dense'),))
    data = vocabulary.to_json()
    assert data == {'version': 1, 'categories': ['spiral', 'line art'],
                    'scales': [{'name': 'density', 'low': 'sparse', 'high': 'dense'}]}
    assert Vocabulary.from_json(data) == vocabulary
    assert Vocabulary.from_json({'version': 1}) == Vocabulary()
    assert dumps(Vocabulary().to_json()) == '{\n  "version": 1,\n  "categories": [],\n  "scales": []\n}\n'


@pytest.mark.parametrize('data, message', [
    ({'version': 2}, 'made by a newer PyLZR'),
    ({'version': 1, 'categories': ['Spiral!']}, r'^categories\[0\]: "Spiral!" is not a category name'),
    ({'version': 1, 'categories': 'spiral'}, '^categories: must be a list'),
    ({'version': 1, 'scales': [{'name': 'density', 'low': 'sparse'}]}, r'^scales\[0\]: "high" is missing'),
    ({'version': 1, 'scales': [{'name': 'density', 'low': 'a', 'high': 'b', 'hi': 'c'}]},
     r'^scales\[0\]: unknown key "hi"'),
    ({'version': 1, 'scales': [{'name': 'Density', 'low': 'a', 'high': 'b'}]}, r'^scales\[0\]: "Density" is not'),
    ({'version': 1, 'categories': ['tunnel']}, '^category "tunnel" is already in the list'),
    ({'version': 1, 'colours': []}, 'unknown key "colours"'),
])
def test_bad_files_say_where(data, message):
    with pytest.raises(VocabularyError, match=message):
        Vocabulary.from_json(data)
