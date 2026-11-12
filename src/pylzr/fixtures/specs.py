"""How mappings are written in a binding file, and how each one becomes a
mapping (mappings.py) by finding its segments in the fixture's profile.

A spec names a channel and a *segment* of it: one of the channel's
capabilities in the profile, picked by any DMX value inside it ("segment":
64 is the Gruolin's 64–127 line scan). The segment's ends come from the
profile, so each DMX range is written down once, and correcting the profile
corrects every binding:

  - a segment with a speed runs slow → fast (its speedStart → speedEnd),
    any other from its first DMX value to its last; "invert": true turns a
    linear or bipolar mapping the other way
  - "segment" may be left out when the channel has just one
  - a gradient mapping needs a proportional segment, one whose properties
    run from a start to an end; a single step is for an options mapping

Plain DMX numbers appear only where they are the point: an option's values,
a zero or off value, a centre, and calibration (min, max, limit, deadband).

  linear     {"type": "linear", "attribute": "size", "channel": "Pattern Size", "invert": true}
  bipolar    {"type": "bipolar", "attribute": "pos_x", "channel": "Horizontal Position", "centre": 128}
  direction  {"type": "direction", "attribute": "spin_z", "channel": "Rotation Z", "forward": 128, "reverse": 192}
  options    {"type": "options", "attribute": "color", "values": {"red": {"Color": 8}, …}}
  selected   {"type": "selected", "selector": "draw_style", "default": "line", "choices": {"line": {…}, …}}

Each may have a "comment". A new type is one spec class here (read,
to_json, build), its line in SPEC_TYPES, and its mapping class.
"""

import difflib
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, ClassVar

from .attributes import NAME_RE
from .errors import BindingError
from .jsonio import ObjectReader, check_type
from .mappings import DMX_MAX, AttributeMapping, Bipolar, Direction, Linear, Options, Selected
from .ofl import Capability, Channel, parse_entity

RELEASE = 'release'      # "zero": "release" — at 0, leave the channel to the next mapping

Channels = Mapping[str, Channel]       # the mode's channels, by key


# ── Reading helpers (errors name the exact key) ─────────────────────────────

def _name(reader: ObjectReader, key: str) -> str:
    name = reader.required(key, str)
    if not NAME_RE.match(name):
        raise reader.fail(f'"{name}" is not an attribute name (lowercase letters, digits and _)', key)
    return name


def _check_dmx(value: int, where: str) -> int:
    if not 0 <= value <= DMX_MAX:
        raise BindingError(f'must be a DMX value 0–{DMX_MAX}, not {value}', where)
    return value


def _dmx(reader: ObjectReader, key: str, required: bool = True) -> int | None:
    value = reader.required(key, int) if required else reader.optional(key, int)
    return None if value is None else _check_dmx(value, reader.path(key))


def _dmx_value(value: Any, where: str) -> int:
    return _check_dmx(check_type(value, int, where, BindingError), where)


def _comment(reader: ObjectReader) -> str:
    return reader.optional('comment', str, '')


def _json(**fields: Any) -> dict:
    """A spec as saved: fields in the given order, None (a default) left out."""
    return {key: value for key, value in fields.items() if value is not None}


# ── Building helpers ────────────────────────────────────────────────────────

def find_channel(channels: Channels, name: str, where: str = 'channel') -> Channel:
    if name not in channels:
        close = difflib.get_close_matches(name, list(channels), n=1)
        hint = f' (did you mean "{close[0]}"?)' if close else ''
        raise BindingError(f'the mode has no channel "{name}"{hint}', where)
    return channels[name]


def _segment(channel: Channel, at: int | None, where: str = 'segment') -> Capability:
    """The capability of `channel` containing DMX value `at`; its only one if `at` is None."""
    if at is None:
        if len(channel.capabilities) != 1:
            raise BindingError(f'"{channel.key}" has {len(channel.capabilities)} segments: say which with '
                               '"segment" (a DMX value inside it)', where)
        return channel.capabilities[0]
    capability = channel.capability_at(at)
    if capability is None:
        raise BindingError(f'"{channel.key}" has no segment at {at}', where)
    return capability


def _gradient(channel: Channel, at: int | None, where: str = 'segment') -> Capability:
    """The segment at `at`, which must be a gradient (proportional, more than one value)."""
    capability = _segment(channel, at, where)
    if capability.start == capability.end or not capability.proportional:
        raise BindingError(f'segment {capability.start}–{capability.end} of "{channel.key}" is a single step '
                           f'({capability.type}), not a gradient: use an options mapping', where)
    return capability


def ends(capability: Capability) -> tuple[int, int]:
    """A segment's (first, last) DMX values in its own direction: slow → fast
    if it has a speed, else low → high."""
    speed = capability.span('speed')
    if speed is not None:
        slow, fast = (abs(parse_entity(value).number) for value in speed)
        if slow > fast:
            return capability.end, capability.start
    return capability.start, capability.end


def _make(cls: Callable[..., AttributeMapping], *args: Any, **kwargs: Any) -> AttributeMapping:
    """cls(*args, **kwargs), with a ValueError turned into a BindingError at the mapping."""
    try:
        return cls(*args, **kwargs)
    except ValueError as e:
        raise BindingError(str(e)) from None


# ── The spec types ──────────────────────────────────────────────────────────

class MappingSpec(ABC):
    """One mapping as written in a binding."""

    TYPE: ClassVar[str]

    @classmethod
    @abstractmethod
    def read(cls, reader: ObjectReader) -> 'MappingSpec':
        """The spec in `reader` (its "type" already read)."""

    @abstractmethod
    def to_json(self) -> dict:
        """The spec as saved (canonical: fixed key order, defaults left out)."""

    @abstractmethod
    def build(self, channels: Channels) -> AttributeMapping:
        """The mapping, with segments looked up in the mode's channels.
        BindingError, at a key inside the spec, if something doesn't fit."""


@dataclass(frozen=True)
class LinearSpec(MappingSpec):
    """A continuous attribute across a gradient segment. "zero": a DMX value
    for exactly 0, or "release" to leave the channel to the next mapping."""

    TYPE: ClassVar[str] = 'linear'

    attribute: str
    channel:   str
    segment:   int | None = None
    invert:    bool = False
    min:       float = 0.0
    max:       float = 1.0
    zero:      int | str | None = None
    comment:   str = ''

    @classmethod
    def read(cls, reader: ObjectReader) -> 'LinearSpec':
        attribute, channel = _name(reader, 'attribute'), reader.required('channel', str)
        segment, invert = _dmx(reader, 'segment', required=False), reader.optional('invert', bool, False)
        low, high = reader.optional('min', float, 0.0), reader.optional('max', float, 1.0)
        zero = reader.optional('zero', (int, str))
        if isinstance(zero, str) and zero != RELEASE:
            raise reader.fail(f'must be a DMX value or "{RELEASE}", not "{zero}"', 'zero')
        if isinstance(zero, int):
            _check_dmx(zero, reader.path('zero'))
        return cls(attribute, channel, segment, invert, low, high, zero, _comment(reader))

    def to_json(self) -> dict:
        return _json(type=self.TYPE, attribute=self.attribute, channel=self.channel, segment=self.segment,
                     invert=self.invert or None, min=self.min if self.min != 0 else None,
                     max=self.max if self.max != 1 else None, zero=self.zero, comment=self.comment or None)

    def build(self, channels: Channels) -> AttributeMapping:
        start, end = ends(_gradient(find_channel(channels, self.channel), self.segment))
        if self.invert:
            start, end = end, start
        zero = self.zero if isinstance(self.zero, int) else None
        return _make(Linear, self.attribute, self.channel, start, end, self.min, self.max, zero,
                     release_at_zero=self.zero == RELEASE)


@dataclass(frozen=True)
class BipolarSpec(MappingSpec):
    """A bipolar attribute across a gradient segment, 0 at `centre`."""

    TYPE: ClassVar[str] = 'bipolar'

    attribute: str
    channel:   str
    centre:    int
    segment:   int | None = None
    limit:     float = 1.0
    invert:    bool = False
    comment:   str = ''

    @classmethod
    def read(cls, reader: ObjectReader) -> 'BipolarSpec':
        return cls(_name(reader, 'attribute'), reader.required('channel', str), _dmx(reader, 'centre'),
                   _dmx(reader, 'segment', required=False), reader.optional('limit', float, 1.0),
                   reader.optional('invert', bool, False), _comment(reader))

    def to_json(self) -> dict:
        return _json(type=self.TYPE, attribute=self.attribute, channel=self.channel, segment=self.segment,
                     centre=self.centre, limit=self.limit if self.limit != 1 else None,
                     invert=self.invert or None, comment=self.comment or None)

    def build(self, channels: Channels) -> AttributeMapping:
        segment = _gradient(find_channel(channels, self.channel), self.segment)
        if not segment.contains(self.centre):
            raise BindingError(f'{self.centre} is outside the segment {segment.start}–{segment.end}', 'centre')
        low, high = ends(segment)
        if self.invert:
            low, high = high, low
        return _make(Bipolar, self.attribute, self.channel, low, self.centre, high, self.limit)


@dataclass(frozen=True)
class DirectionSpec(MappingSpec):
    """A bipolar speed: + through the `forward` segment, − through `reverse`.
    With no `off` value it leaves the channel to the next mapping at 0."""

    TYPE: ClassVar[str] = 'direction'

    attribute: str
    channel:   str
    forward:   int
    reverse:   int
    off:       int | None = None
    deadband:  float = 0.0
    comment:   str = ''

    @classmethod
    def read(cls, reader: ObjectReader) -> 'DirectionSpec':
        return cls(_name(reader, 'attribute'), reader.required('channel', str), _dmx(reader, 'forward'),
                   _dmx(reader, 'reverse'), _dmx(reader, 'off', required=False),
                   reader.optional('deadband', float, 0.0), _comment(reader))

    def to_json(self) -> dict:
        return _json(type=self.TYPE, attribute=self.attribute, channel=self.channel, forward=self.forward,
                     reverse=self.reverse, off=self.off, deadband=self.deadband or None,
                     comment=self.comment or None)

    def build(self, channels: Channels) -> AttributeMapping:
        channel = find_channel(channels, self.channel)
        forward = _gradient(channel, self.forward, 'forward')
        reverse = _gradient(channel, self.reverse, 'reverse')
        if forward == reverse:
            raise BindingError(f'forward and reverse are the same segment ({forward.start}–{forward.end})',
                               'reverse')
        return _make(Direction, self.attribute, self.channel, ends(forward), ends(reverse), self.off,
                     self.deadband)


@dataclass(frozen=True)
class OptionsSpec(MappingSpec):
    """An option attribute: each choice sets DMX values on one or more channels."""

    TYPE: ClassVar[str] = 'options'

    attribute: str
    values:    Mapping[str, Mapping[str, int]]
    comment:   str = ''

    def __post_init__(self):
        object.__setattr__(self, 'values', MappingProxyType(
            {choice: MappingProxyType(dict(settings)) for choice, settings in self.values.items()}))

    @classmethod
    def read(cls, reader: ObjectReader) -> 'OptionsSpec':
        attribute = _name(reader, 'attribute')
        values_reader = reader.child('values')
        values = {}
        for choice in values_reader.keys():
            if not NAME_RE.match(choice):
                raise values_reader.fail(f'"{choice}" is not a choice name (lowercase letters, digits and _)', choice)
            settings = values_reader.child(choice)
            values[choice] = {ch: _dmx_value(v, settings.path(ch)) for ch, v in settings.rest().items()}
        return cls(attribute, values, _comment(reader))        # no choices, or an empty one: reported by build()

    def to_json(self) -> dict:
        return _json(type=self.TYPE, attribute=self.attribute,
                     values={choice: dict(settings) for choice, settings in self.values.items()},
                     comment=self.comment or None)

    def build(self, channels: Channels) -> AttributeMapping:
        for choice, settings in self.values.items():
            for name in settings:
                find_channel(channels, name, f'values.{choice}.{name}')
        return _make(Options, self.attribute, self.values)


@dataclass(frozen=True)
class SelectedSpec(MappingSpec):
    """An option attribute (the selector) picks which inner mapping is used."""

    TYPE: ClassVar[str] = 'selected'

    selector: str
    default:  str
    choices:  Mapping[str, MappingSpec] = field(default_factory=dict)
    comment:  str = ''

    def __post_init__(self):
        object.__setattr__(self, 'choices', MappingProxyType(dict(self.choices)))

    @classmethod
    def read(cls, reader: ObjectReader) -> 'SelectedSpec':
        selector, default = _name(reader, 'selector'), reader.required('default', str)
        choices_reader = reader.child('choices')
        choices = {}
        for choice in choices_reader.keys():
            if not NAME_RE.match(choice):
                raise choices_reader.fail(f'"{choice}" is not a choice name (lowercase letters, digits and _)', choice)
            choices[choice] = read_spec(choices_reader.child(choice))
        return cls(selector, default, choices, _comment(reader))

    def to_json(self) -> dict:
        return _json(type=self.TYPE, selector=self.selector, default=self.default,
                     choices={choice: spec.to_json() for choice, spec in self.choices.items()},
                     comment=self.comment or None)

    def build(self, channels: Channels) -> AttributeMapping:
        built = {}
        for choice, spec in self.choices.items():
            try:
                built[choice] = spec.build(channels)
            except BindingError as e:
                raise e.within(f'choices.{choice}') from None
        return _make(Selected, self.selector, built, self.default)


SPEC_TYPES: Mapping[str, type[MappingSpec]] = MappingProxyType(
    {spec.TYPE: spec for spec in (LinearSpec, BipolarSpec, DirectionSpec, OptionsSpec, SelectedSpec)})


def read_spec(reader: ObjectReader) -> MappingSpec:
    """The mapping spec in `reader`, by its "type"."""
    kind = reader.required('type', str)
    if kind not in SPEC_TYPES:
        close = difflib.get_close_matches(kind, list(SPEC_TYPES), n=1)
        hint = f' (did you mean "{close[0]}"?)' if close else f' (one of: {", ".join(SPEC_TYPES)})'
        raise reader.fail(f'unknown mapping type "{kind}"{hint}', 'type')
    spec = SPEC_TYPES[kind].read(reader)
    reader.finish()
    return spec
