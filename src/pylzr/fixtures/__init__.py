"""What fixtures are and how PyLZR drives them, kept free of Qt, sockets
and audio (tests/test_architecture.py checks this):

  attributes   the fixture-independent controls everything creative speaks
  vocabulary   pattern categories and scales, shared by every laser
  ofl          fixture profiles in the Open Fixture Library format
  mappings     how attribute values become DMX values (one class per kind of segment)
  patterns     the pattern library: tagged patterns, matched by category and scales
  specs        how mappings are written in a binding, built from the profile's segments
  binding      a fixture type: profile + mode + mappings + patterns, checked for safety
  renderer     a whole attribute state → one fixture's channel values
  patch        which fixtures are at which addresses, and rendering them (Rig)
  library      every profile and binding (shipped + your folder), your patch and words
  jsonio       strict reading and safe writing of the data files
  errors       FixtureError and friends, naming file and place
"""

from .attributes import (
    CORE, CORE_ATTRIBUTES, AttrKey, Attribute, AttributeSet, Kind, PatternRequest, make_extra,
)
from .binding import Binding, ResolvedBinding, load_binding, read_binding, write_binding
from .errors import BindingError, FixtureError, PatchError, ProfileError, VocabularyError
from .library import FixtureLibrary, Problem
from .mappings import AttributeMapping, Bipolar, Direction, Linear, Options, Selected
from .ofl import Capability, Channel, Entity, Mode, Profile, load_profile, parse_entity, read_profile
from .patch import Patch, PatchEntry, PatchProblem, Rig, load_patch, read_patch, write_patch
from .patterns import PatternEntry, PatternLibrary, PatternMapping
from .renderer import Render, Renderer, compile_fixture
from .specs import (
    SPEC_TYPES, BipolarSpec, DirectionSpec, LinearSpec, MappingSpec, OptionsSpec, SelectedSpec, read_spec,
)
from .vocabulary import LEVELS, STARTER_CATEGORIES, STARTER_SCALES, Scale, Vocabulary, level_value, value_level

__all__ = [
    'CORE', 'CORE_ATTRIBUTES', 'AttrKey', 'Attribute', 'AttributeSet', 'Kind', 'PatternRequest', 'make_extra',
    'Binding', 'ResolvedBinding', 'load_binding', 'read_binding', 'write_binding',
    'BindingError', 'FixtureError', 'PatchError', 'ProfileError', 'VocabularyError',
    'FixtureLibrary', 'Problem',
    'AttributeMapping', 'Bipolar', 'Direction', 'Linear', 'Options', 'Selected',
    'Patch', 'PatchEntry', 'PatchProblem', 'Rig', 'load_patch', 'read_patch', 'write_patch',
    'PatternEntry', 'PatternLibrary', 'PatternMapping',
    'Render', 'Renderer', 'compile_fixture',
    'SPEC_TYPES', 'BipolarSpec', 'DirectionSpec', 'LinearSpec', 'MappingSpec', 'OptionsSpec', 'SelectedSpec',
    'read_spec',
    'Capability', 'Channel', 'Entity', 'Mode', 'Profile', 'load_profile', 'parse_entity', 'read_profile',
    'LEVELS', 'STARTER_CATEGORIES', 'STARTER_SCALES', 'Scale', 'Vocabulary', 'level_value', 'value_level',
]
