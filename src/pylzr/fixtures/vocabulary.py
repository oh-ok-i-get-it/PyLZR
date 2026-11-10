"""Words for describing patterns, shared by every laser:

  categories  what a pattern is, e.g. tunnel
  scales      how it feels, from a low to a high end, e.g. energy: calm → intense

PyLZR ships a starter list of each; your own additions are kept in
vocabulary.json in your fixtures folder and work exactly the same. Because
every laser's patterns are tagged with the same words, one show can ask for
"a tunnel, energy 4" on any laser.

A scale is rated in LEVELS (1–5) and stored as level / 5 (0.2 … 1.0), so a
finer scale later wouldn't change saved files.
"""

import re
from dataclasses import dataclass
from typing import Any

from .attributes import NAME_RE
from .errors import VocabularyError
from .jsonio import ObjectReader, upgrade

VERSION = 1
LEVELS  = 5

CATEGORY_RE  = re.compile(r'[a-z0-9]+([ _-][a-z0-9]+)*\Z')   # e.g. 'tunnel', 'line art'
MAX_NAME     = 32
MAX_LABEL    = 24


def normalize_name(text: str) -> str:
    """A typed category name in its stored form: trimmed, lowercase, single
    spaces ('  Line  Art ' → 'line art')."""
    return ' '.join(text.split()).lower()


def level_value(level: int) -> float:
    """A rating (1–5) as stored (0.2–1.0)."""
    if isinstance(level, bool) or not isinstance(level, int) or not 1 <= level <= LEVELS:
        raise ValueError(f'a level is a whole number from 1 to {LEVELS}, not {level!r}')
    return level / LEVELS


def value_level(value: float) -> int:
    """A stored scale value as the nearest rating (1–5)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1:
        raise ValueError(f'a scale value is a number above 0, up to 1, not {value!r}')
    return max(1, min(LEVELS, round(value * LEVELS)))


def check_category(name: str) -> str:
    if not isinstance(name, str) or len(name) > MAX_NAME or not CATEGORY_RE.match(name):
        raise ValueError(f'"{name}" is not a category name (lowercase words, up to {MAX_NAME} characters)')
    return name


@dataclass(frozen=True)
class Scale:
    """A way of rating patterns, from `low` (level 1) to `high` (level 5)."""

    name: str      # e.g. 'energy' (used in files and pattern requests)
    low:  str      # e.g. 'calm'
    high: str      # e.g. 'intense'

    def __post_init__(self):
        if not isinstance(self.name, str) or len(self.name) > MAX_NAME or not NAME_RE.match(self.name):
            raise ValueError(f'"{self.name}" is not a scale name (lowercase letters, digits and _)')
        for end in (self.low, self.high):
            if not isinstance(end, str) or not end.strip() or len(end) > MAX_LABEL:
                raise ValueError(f'scale "{self.name}" needs low and high labels of 1–{MAX_LABEL} characters')


STARTER_CATEGORIES: tuple[str, ...] = (
    'line', 'tunnel', 'circle', 'wave', 'star', 'grid', 'text', 'abstract', 'animation')

STARTER_SCALES: tuple[Scale, ...] = (
    Scale('energy',     'calm',   'intense'),
    Scale('sharpness',  'smooth', 'sharp'),
    Scale('complexity', 'simple', 'complex'),
)


@dataclass(frozen=True)
class Vocabulary:
    """The starter words plus your own (own_categories, own_scales).
    `categories` and `scales` list both, starters first."""

    own_categories: tuple[str, ...] = ()
    own_scales:     tuple[Scale, ...] = ()

    def __post_init__(self):
        object.__setattr__(self, 'own_categories', tuple(self.own_categories))
        object.__setattr__(self, 'own_scales', tuple(self.own_scales))
        seen = set(STARTER_CATEGORIES)
        for name in self.own_categories:
            check_category(name)
            if name in seen:
                raise ValueError(f'category "{name}" is already in the list')
            seen.add(name)
        seen = {scale.name for scale in STARTER_SCALES}
        for scale in self.own_scales:
            if scale.name in seen:
                raise ValueError(f'scale "{scale.name}" is already in the list')
            seen.add(scale.name)

    @property
    def categories(self) -> tuple[str, ...]:
        return STARTER_CATEGORIES + self.own_categories

    @property
    def scales(self) -> tuple[Scale, ...]:
        return STARTER_SCALES + self.own_scales

    def has_category(self, name: str) -> bool:
        return name in self.categories

    def scale(self, name: str) -> Scale | None:
        return next((scale for scale in self.scales if scale.name == name), None)

    def with_category(self, name: str) -> 'Vocabulary':
        """This vocabulary plus your new category (typed text is normalised)."""
        return Vocabulary(self.own_categories + (normalize_name(name),), self.own_scales)

    def with_scale(self, scale: Scale) -> 'Vocabulary':
        return Vocabulary(self.own_categories, self.own_scales + (scale,))

    # ── vocabulary.json ─────────────────────────────────────────────────

    def to_json(self) -> dict:
        """Your own words, as saved in vocabulary.json."""
        return {
            'version': VERSION,
            'categories': list(self.own_categories),
            'scales': [{'name': s.name, 'low': s.low, 'high': s.high} for s in self.own_scales],
        }

    @classmethod
    def from_json(cls, data: Any) -> 'Vocabulary':
        reader = ObjectReader(upgrade(data, VERSION, error=VocabularyError), error=VocabularyError)
        reader.required('version', int)
        categories = [_checked(check_category, reader.path('categories') + f'[{i}]', name)
                      for i, name in enumerate(reader.optional('categories', list, []))]
        scales = []
        for item in reader.each('scales', required=False):
            name, low, high = (item.required(key, str) for key in ('name', 'low', 'high'))
            item.finish()
            scales.append(_checked(Scale, item.where, name, low, high))
        reader.finish()
        return _checked(cls, '', tuple(categories), tuple(scales))


def _checked(make, where: str, *args):
    """make(*args), with a ValueError turned into a VocabularyError at `where`."""
    try:
        return make(*args)
    except VocabularyError:
        raise
    except ValueError as e:
        raise VocabularyError(str(e), where) from None
