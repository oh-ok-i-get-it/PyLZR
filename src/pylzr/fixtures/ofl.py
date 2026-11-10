"""Fixture profiles in the Open Fixture Library (OFL) format: what each
channel's DMX ranges do. https://open-fixture-library.org (MIT licence);
format: docs/fixture-format.md and docs/capability-types.md in its GitHub
repository.

A profile lists `availableChannels`, each made of capabilities: a DMX range
(`dmxRange`) and a `type` such as Zoom, BeamPosition or ColorPreset, plus
type-specific properties. A property is either one value ("stepped", e.g.
"speed": "fast") or a start and end across the range ("proportional", e.g.
"speedStart": "slow", "speedEnd": "fast"). `modes` say which channels a
fixture has, in order, in each of its DMX modes.

PyLZR reads the parts of the format that DMX lasers use. Everything else is
refused with a clear message rather than misread: 16-bit channels
(fineChannelAliases), switching channels, and pixel/matrix fixtures.
"""

import difflib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .errors import ProfileError, join_where
from .jsonio import ObjectReader, check_type, describe, read_file

DMX_MAX = 255

CAPABILITY_TYPES = (
    'NoFunction', 'ShutterStrobe', 'StrobeSpeed', 'StrobeDuration', 'Intensity', 'ColorIntensity',
    'ColorPreset', 'ColorTemperature', 'Pan', 'PanContinuous', 'Tilt', 'TiltContinuous', 'PanTiltSpeed',
    'WheelSlot', 'WheelShake', 'WheelSlotRotation', 'WheelRotation', 'Effect', 'EffectSpeed',
    'EffectDuration', 'EffectParameter', 'SoundSensitivity', 'BeamAngle', 'BeamPosition', 'Focus', 'Zoom',
    'Iris', 'IrisEffect', 'Frost', 'FrostEffect', 'Prism', 'PrismRotation', 'BladeInsertion',
    'BladeRotation', 'BladeSystemRotation', 'Fog', 'FogOutput', 'FogType', 'Rotation', 'Speed', 'Time',
    'Maintenance', 'Generic',
)

# Every type-specific capability property (each may also come as …Start /
# …End where OFL allows), and those whose values are entities: a number
# with a unit, or a keyword like "fast".
PROPERTIES = frozenset({
    'shutterEffect', 'soundControlled', 'speed', 'duration', 'randomTiming', 'brightness', 'color', 'colors',
    'colorTemperature', 'angle', 'slotNumber', 'wheel', 'isShaking', 'shakeSpeed', 'shakeAngle', 'effectName',
    'effectPreset', 'parameter', 'soundSensitivity', 'horizontalAngle', 'verticalAngle', 'distance',
    'openPercent', 'frostIntensity', 'blade', 'insertion', 'fogType', 'fogOutput', 'time', 'hold',
})
ENTITY_PROPERTIES = frozenset({
    'speed', 'duration', 'time', 'angle', 'horizontalAngle', 'verticalAngle', 'distance', 'brightness',
    'colorTemperature', 'fogOutput', 'openPercent', 'frostIntensity', 'insertion', 'shakeSpeed',
    'shakeAngle', 'parameter', 'soundSensitivity', 'slotNumber', 'hold',
})

# Keywords stand for percentages. OFL defines them per kind of entity (speed,
# angle, …), but no word means different things in different kinds, so one
# table serves them all.
ENTITY_KEYWORDS = MappingProxyType({
    'fast reverse': -100, 'slow reverse': -1, 'stop': 0, 'slow': 1, 'fast': 100,
    'fast CCW': -100, 'slow CCW': -1, 'slow CW': 1, 'fast CW': 100,
    'instant': 0, 'short': 1, 'long': 100,
    'near': 1, 'far': 100,
    'off': 0, 'dark': 1, 'bright': 100,
    'warm': -100, 'CTO': -100, 'default': 0, 'cold': 100, 'CTB': 100,
    'weak': 1, 'strong': 100,
    'closed': 0, 'narrow': 1, 'wide': 100,
    'left': -100, 'center': 0, 'right': 100, 'top': -100, 'bottom': 100,
    'low': 1, 'high': 100, 'small': 1, 'big': 100,
    'out': 0, 'in': 100, 'open': 100,
})

_ENTITY_RE = re.compile(r'(-?\d+(?:\.\d+)?)(%|Hz|bpm|rpm|ms|s|m\^3/min|m|lm|K|deg)?\Z')

# Valid OFL that PyLZR can't use yet. Any key not in the format at all is
# reported as a typo.
_UNSUPPORTED = {
    'templateChannels':   'pixel fixtures (templateChannels)',
    'matrix':             'pixel fixtures (matrix)',
    'fineChannelAliases': '16-bit channels (fineChannelAliases)',
    'switchChannels':     'switching channels (switchChannels)',
}


@dataclass(frozen=True)
class Entity:
    """An OFL value: a number and its unit. Keywords are percentages
    ("fast" is 100 %, "slow CCW" is -1 %). Unit '' is a bare number (e.g.
    a wheel slot number)."""

    number: float
    unit:   str


def parse_entity(value: Any) -> Entity:
    """'fast' → Entity(100, '%'); '10Hz' → Entity(10, 'Hz'); '-10deg' →
    Entity(-10, 'deg'); 3 → Entity(3, ''). ValueError if it's none of these."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return Entity(float(value), '')
    if isinstance(value, str):
        if value in ENTITY_KEYWORDS:
            return Entity(float(ENTITY_KEYWORDS[value]), '%')
        match = _ENTITY_RE.match(value)
        if match:
            return Entity(float(match.group(1)), match.group(2) or '')
    raise ValueError(f'{describe(value)} is not an OFL value (e.g. "fast", "50%", "10Hz", "-10deg")')


@dataclass(frozen=True)
class Capability:
    """What one DMX range of a channel does."""

    start:      int                   # first DMX value (inclusive)
    end:        int                   # last DMX value (inclusive)
    type:       str                   # one of CAPABILITY_TYPES
    properties:  Mapping[str, Any]    # type-specific, as in the file (e.g. {'speedStart': 'slow', …})
    comment:     str = ''
    help_wanted: str = ''             # what the profile's author wasn't sure of (OFL's "helpWanted")

    def contains(self, value: int) -> bool:
        return self.start <= value <= self.end

    @property
    def proportional(self) -> bool:
        """True if some property runs from a start to an end value across the range."""
        return any(name.endswith('Start') for name in self.properties)

    def span(self, name: str) -> tuple[Any, Any] | None:
        """(start, end) of property `name` across the range, as in the file:
        a stepped property gives (value, value). None if it isn't there."""
        if name in self.properties:
            return self.properties[name], self.properties[name]
        if f'{name}Start' in self.properties:
            return self.properties[f'{name}Start'], self.properties[f'{name}End']
        return None


@dataclass(frozen=True)
class Channel:
    """One channel: its capabilities in DMX order. Values in a gap between
    capabilities are unknown (capability_at() gives None)."""

    key:           str
    capabilities:  tuple[Capability, ...]
    default_value: int = 0

    def capability_at(self, value: int) -> Capability | None:
        return next((cap for cap in self.capabilities if cap.contains(value)), None)


@dataclass(frozen=True)
class Mode:
    """One DMX mode: the channel at each offset (None: an unused slot)."""

    name:       str
    short_name: str
    channels:   tuple[str | None, ...]

    @property
    def footprint(self) -> int:
        """How many DMX channels the fixture takes in this mode."""
        return len(self.channels)

    def offset(self, key: str) -> int:
        """0-based position of channel `key` in this mode."""
        try:
            return self.channels.index(key)
        except ValueError:
            raise KeyError(f'mode "{self.name}" has no channel "{key}"') from None


@dataclass(frozen=True)
class Profile:
    """A fixture profile. `key` is where it lives, e.g.
    'gruolin/rgb-fullcolor-beam-effect-light' ('' if loaded from data)."""

    key:        str
    name:       str
    short_name: str
    categories: tuple[str, ...]
    channels:   Mapping[str, Channel]
    modes:      tuple[Mode, ...]

    def mode(self, name: str) -> Mode:
        """The mode called `name` or with that short name (e.g. '36ch')."""
        for mode in self.modes:
            if name in (mode.name, mode.short_name):
                return mode
        names = ', '.join(mode.short_name for mode in self.modes)
        raise KeyError(f'{self.name} has no mode "{name}" (it has: {names})')


# ── Loading ─────────────────────────────────────────────────────────────────

def read_profile(path: Path | str, key: str = '') -> Profile:
    """The profile in the file at `path`. Problems raise ProfileError naming the file."""
    data = read_file(path, ProfileError)
    try:
        return load_profile(data, key)
    except ProfileError as e:
        raise e.in_file(str(path)) from None


def load_profile(data: Any, key: str = '') -> Profile:
    """A Profile from OFL JSON data (already parsed). Raises ProfileError."""
    reader = ObjectReader(data, error=ProfileError)
    for unsupported in ('templateChannels', 'matrix'):
        if reader.has(unsupported):
            raise reader.fail(f'uses {_UNSUPPORTED[unsupported]}, which PyLZR doesn\'t support yet')
    name = reader.required('name', str)
    short_name = reader.optional('shortName', str, name)
    categories = tuple(reader.required('categories', list))
    for i, category in enumerate(categories):
        check_type(category, str, join_where(reader.path('categories'), f'[{i}]'), ProfileError)
    if not categories:
        raise reader.fail('needs at least one category', 'categories')
    for ignored in ('$schema', 'meta', 'comment', 'helpWanted', 'links', 'rdm', 'physical', 'wheels'):
        reader.has(ignored)             # valid OFL, not used by PyLZR

    channels_reader = reader.child('availableChannels')
    channels = {channel: _load_channel(channel, channels_reader.child(channel))
                for channel in channels_reader.keys()}
    if not channels:
        raise reader.fail('needs at least one channel', 'availableChannels')

    modes = tuple(_load_mode(item, channels) for item in reader.each('modes'))
    if not modes:
        raise reader.fail('needs at least one mode', 'modes')
    _check_unique([m.name for m in modes], 'name', reader.path('modes'))
    _check_unique([m.short_name for m in modes], 'shortName', reader.path('modes'))
    reader.finish()
    return Profile(key, name, short_name, categories, MappingProxyType(channels), modes)


def _load_channel(key: str, reader: ObjectReader) -> Channel:
    if reader.has('fineChannelAliases'):
        raise reader.fail(f'uses {_UNSUPPORTED["fineChannelAliases"]}, which PyLZR doesn\'t support yet')
    resolution = reader.optional('dmxValueResolution', str, '8bit')
    if resolution != '8bit':
        raise reader.fail(f'dmxValueResolution "{resolution}" isn\'t supported (only 8bit)', 'dmxValueResolution')

    single, several = reader.has('capability'), reader.has('capabilities')
    if single == several:
        raise reader.fail('needs either "capability" or "capabilities"')
    if single:
        capabilities = (_load_capability(reader.child('capability'), whole_range=True),)
    else:
        capabilities = tuple(_load_capability(item) for item in reader.each('capabilities'))
        if not capabilities:
            raise reader.fail('needs at least one capability', 'capabilities')
        for i, (before, after) in enumerate(zip(capabilities, capabilities[1:], strict=False)):
            if after.start <= before.end:
                where = join_where(reader.path('capabilities'), f'[{i + 1}]')
                raise ProfileError(f'range {after.start}–{after.end} must start after the previous one '
                                   f'({before.start}–{before.end})', where)

    default = _dmx_value(reader.optional('defaultValue', (int, str), 0), reader.path('defaultValue'))
    highlight = reader.optional('highlightValue', (int, str), DMX_MAX)
    _dmx_value(highlight, reader.path('highlightValue'))
    reader.optional('constant', bool)
    precedence = reader.optional('precedence', str, 'LTP')
    if precedence not in ('HTP', 'LTP'):
        raise reader.fail(f'must be HTP or LTP, not "{precedence}"', 'precedence')
    reader.finish()
    return Channel(key, capabilities, default)


def _dmx_value(value: int | str, where: str) -> int:
    """A DMX value given as a number (0–255) or a percentage ("50%")."""
    if isinstance(value, str):
        match = re.fullmatch(r'(\d+(?:\.\d+)?)%', value)
        if not match or float(match.group(1)) > 100:
            raise ProfileError(f'must be 0–255 or a percentage, not "{value}"', where)
        return int(float(match.group(1)) * DMX_MAX / 100 + 0.5)
    if not 0 <= value <= DMX_MAX:
        raise ProfileError(f'must be 0–255, not {value}', where)
    return value


def _load_capability(reader: ObjectReader, whole_range: bool = False) -> Capability:
    if reader.has('switchChannels'):
        raise reader.fail(f'uses {_UNSUPPORTED["switchChannels"]}, which PyLZR doesn\'t support yet')
    if whole_range and not reader.has('dmxRange'):
        start, end = 0, DMX_MAX
    else:
        start, end = _dmx_range(reader.required('dmxRange', list), reader.path('dmxRange'))
    kind = reader.required('type', str)
    if kind not in CAPABILITY_TYPES:
        close = difflib.get_close_matches(kind, CAPABILITY_TYPES, n=1)
        hint = f' (did you mean "{close[0]}"?)' if close else ''
        raise reader.fail(f'unknown capability type "{kind}"{hint}', 'type')
    comment = reader.optional('comment', str, '')
    help_wanted = reader.optional('helpWanted', str, '')
    menu_click = reader.optional('menuClick', str, 'start')
    if menu_click not in ('start', 'center', 'end', 'hidden'):
        raise reader.fail(f'must be start, center, end or hidden, not "{menu_click}"', 'menuClick')

    properties = reader.rest()          # the type-specific ones, checked below
    _check_properties(properties, reader)
    reader.finish()
    return Capability(start, end, kind, MappingProxyType(properties), comment, help_wanted)


def _dmx_range(value: list, where: str) -> tuple[int, int]:
    if (len(value) != 2 or any(isinstance(v, bool) or not isinstance(v, int) for v in value)
            or not 0 <= value[0] <= value[1] <= DMX_MAX):
        raise ProfileError(f'must be [first, last] with 0 ≤ first ≤ last ≤ 255, not {value}', where)
    return value[0], value[1]


def _check_properties(properties: dict, reader: ObjectReader):
    """Known property names only; Start/End come in pairs and never with the
    plain property; entity values must parse."""
    for name, value in properties.items():
        base = name.removesuffix('Start').removesuffix('End')
        if base not in PROPERTIES:
            known = sorted(PROPERTIES | {p + end for p in ENTITY_PROPERTIES for end in ('Start', 'End')})
            close = difflib.get_close_matches(name, known, n=1)
            hint = f' (did you mean "{close[0]}"?)' if close else ''
            raise reader.fail(f'unknown capability property "{name}"{hint}', name)
        if name != base:
            partner = base + ('End' if name.endswith('Start') else 'Start')
            if partner not in properties:
                raise reader.fail(f'"{name}" needs "{partner}" too', name)
            if base in properties:
                raise reader.fail(f'"{base}" can\'t be given with "{name}"', name)
        if base in ENTITY_PROPERTIES:
            try:
                parse_entity(value)
            except ValueError as e:
                raise reader.fail(str(e), name) from None


def _load_mode(reader: ObjectReader, channels: Mapping[str, Channel]) -> Mode:
    name = reader.required('name', str)
    short_name = reader.optional('shortName', str, name)
    keys = []
    for i, entry in enumerate(reader.required('channels', list)):
        where = join_where(reader.path('channels'), f'[{i}]')
        if isinstance(entry, dict):
            raise ProfileError('uses matrix channel inserts (pixel fixtures), which PyLZR doesn\'t support yet',
                               where)
        if entry is not None:
            check_type(entry, str, where, ProfileError)
            if entry not in channels:
                close = difflib.get_close_matches(entry, list(channels), n=1)
                hint = f' (did you mean "{close[0]}"?)' if close else ''
                raise ProfileError(f'no channel "{entry}" in availableChannels{hint}', where)
            if entry in keys:
                raise ProfileError(f'channel "{entry}" is used twice in this mode', where)
        keys.append(entry)
    if not keys:
        raise reader.fail('needs at least one channel', 'channels')
    reader.optional('rdmPersonalityIndex', int)
    reader.optional('physical', dict)
    reader.finish()
    return Mode(name, short_name, tuple(keys))


def _check_unique(values: list[str], field: str, where: str):
    for i, value in enumerate(values):
        if value in values[:i]:
            raise ProfileError(f'two modes have the {field} "{value}"', join_where(where, f'[{i}]'))
