"""What fixtures are and how PyLZR drives them, kept free of Qt, sockets
and audio (tests/test_architecture.py checks this):

  attributes   the fixture-independent controls everything creative speaks
  vocabulary   pattern categories and scales, shared by every laser
  jsonio       strict reading and safe writing of the data files
  errors       FixtureError and friends, naming file and place
"""

from .attributes import (
    CORE, CORE_ATTRIBUTES, AttrKey, Attribute, AttributeSet, Kind, PatternRequest, make_extra,
)
from .errors import BindingError, FixtureError, PatchError, ProfileError, VocabularyError
from .vocabulary import LEVELS, STARTER_CATEGORIES, STARTER_SCALES, Scale, Vocabulary, level_value, value_level

__all__ = [
    'CORE', 'CORE_ATTRIBUTES', 'AttrKey', 'Attribute', 'AttributeSet', 'Kind', 'PatternRequest', 'make_extra',
    'BindingError', 'FixtureError', 'PatchError', 'ProfileError', 'VocabularyError',
    'LEVELS', 'STARTER_CATEGORIES', 'STARTER_SCALES', 'Scale', 'Vocabulary', 'level_value', 'value_level',
]
