"""Bindings: how PyLZR's attributes drive one kind of fixture in one of its
DMX modes. A binding file is what a patch calls a fixture type:
bindings/gruolin/rgb-beam-36ch.json is the type 'gruolin/rgb-beam-36ch'.

  {"version": 1, "name": "Gruolin RGB Beam (36ch)",
   "profile": "gruolin/rgb-fullcolor-beam-effect-light", "mode": "36ch",
   "layers": {"a": 0, "b": 17},      a second pattern output, 17 channels on
   "base": {"Auto Speed": 0},        values for channels nothing drives
   "extras": [ … ],                  this fixture's own x_ attributes
   "mappings": [ … ],                in priority order (specs.py)
   "patterns": {"channels": […], "none": {…}, "library": […]}}   (patterns.py)

Two steps:
  load     the file's shape: keys, types, values (read_binding, load_binding)
  resolve  its meaning, against the profile (Binding.resolve): every channel
           and segment exists, attributes and their choices are known, the
           layers line up, and the safety rules hold

Safety rules, checked on every value a mapping could ever send (outputs()),
on every layer:
  - each value is on a segment the profile describes (no gaps)
  - never a Maintenance segment (e.g. a reset range)
  - a NoFunction segment only for an off value (a zero, an off, a choice
    called off or none, "no pattern", or a base value)

Layers: mappings name layer a's channels; layer b uses the channel as many
places further on as its offset, which must have the same segments (this
catches a wrong offset). Pattern channels are exempt from that comparison
(the Gruolin's second pattern has no dynamic effects) and no other mapping
may use them; every pattern's values are checked on every layer instead.
Base values and attributes of the whole fixture (power) are never shifted.

When several mappings share a channel, the first active one gets it (the
renderer's job); the pattern mapping always comes first.

Saving writes the canonical form (keys in a fixed order, defaults left out),
so a saved file loads and saves back to the same bytes.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any

from .attributes import DEFAULT_LAYER, Attribute, AttributeSet, make_extra
from .errors import BindingError, join_where
from .jsonio import ObjectReader, check_type, read_file, upgrade, write_file
from .mappings import DMX_MAX, AttributeMapping
from .ofl import Channel, Mode, Profile
from .patterns import PatternLibrary, PatternMapping
from .specs import MappingSpec, find_channel, read_spec

VERSION = 1

_LAYER_NAMES = 'abcdefghijklmnopqrstuvwxyz'


def _check_layers(layers: Mapping[str, int]) -> MappingProxyType:
    """Layers a, b, c, … in order, starting with "a": 0, each further on."""
    items = list(dict(layers).items())
    if not items or items[0] != (DEFAULT_LAYER, 0):
        raise BindingError('must start with "a": 0', 'layers')
    for i, (name, offset) in enumerate(items):
        where = join_where('layers', str(name))
        if i >= len(_LAYER_NAMES) or name != _LAYER_NAMES[i]:
            raise BindingError('layers are named a, b, c, … in order', where)
        if isinstance(offset, bool) or not isinstance(offset, int):
            raise BindingError(f'must be a whole number of channels, not {offset!r}', where)
        if i and offset <= items[i - 1][1]:
            raise BindingError('each layer must start further on than the one before', where)
    return MappingProxyType(dict(items))


def _check_base(base: Mapping[str, int]) -> MappingProxyType:
    for channel, value in base.items():
        where = join_where('base', str(channel))
        if not isinstance(channel, str) or not channel:
            raise BindingError(f'{channel!r} is not a channel name', where)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= DMX_MAX:
            raise BindingError(f'must be a DMX value 0–{DMX_MAX}, not {value!r}', where)
    return MappingProxyType(dict(base))


@dataclass(frozen=True)
class Binding:
    """A binding as written in its file. `key` is where it lives, e.g.
    'gruolin/rgb-beam-36ch' ('' if loaded from data)."""

    name:     str
    profile:  str                                     # the profile's key
    mode:     str                                     # its mode's name or short name
    mappings: tuple[MappingSpec, ...] = ()
    layers:   Mapping[str, int] = field(default_factory=lambda: {DEFAULT_LAYER: 0})
    base:     Mapping[str, int] = field(default_factory=dict)
    extras:   tuple[Attribute, ...] = ()
    patterns: PatternLibrary | None = None
    comment:  str = ''
    key:      str = ''

    def __post_init__(self):
        for name in ('name', 'profile', 'mode'):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise BindingError(f'must be some text, not {value!r}', name)
        object.__setattr__(self, 'layers', _check_layers(self.layers))
        object.__setattr__(self, 'base', _check_base(self.base))
        object.__setattr__(self, 'extras', tuple(self.extras))
        try:
            AttributeSet(self.extras)
        except ValueError as e:
            raise BindingError(str(e), 'extras') from None
        object.__setattr__(self, 'mappings', tuple(self.mappings))
        for i, spec in enumerate(self.mappings):
            if not isinstance(spec, MappingSpec):
                raise BindingError(f'must be a mapping spec, not {spec!r}', f'mappings[{i}]')

    def with_patterns(self, patterns: PatternLibrary) -> 'Binding':
        """This binding with another pattern library (e.g. after tagging)."""
        return replace(self, patterns=patterns)

    def resolve(self, profile: Profile) -> 'ResolvedBinding':
        """Check this binding against its profile and build its mappings.
        BindingError, naming the place in the binding, if anything doesn't fit."""
        return _resolve(self, profile)

    def to_json(self) -> dict:
        data: dict[str, Any] = {'version': VERSION, 'name': self.name}
        if self.comment:
            data['comment'] = self.comment
        data['profile'], data['mode'] = self.profile, self.mode
        if dict(self.layers) != {DEFAULT_LAYER: 0}:
            data['layers'] = dict(self.layers)
        if self.base:
            data['base'] = dict(self.base)
        if self.extras:
            data['extras'] = [_extra_json(extra) for extra in self.extras]
        data['mappings'] = [spec.to_json() for spec in self.mappings]
        if self.patterns is not None:
            data['patterns'] = self.patterns.to_json()
        return data


# ── Files ───────────────────────────────────────────────────────────────────

def read_binding(path: Path | str, key: str = '') -> Binding:
    """The binding in the file at `path`. Problems raise BindingError naming the file."""
    data = read_file(path, BindingError)
    try:
        return load_binding(data, key)
    except BindingError as e:
        raise e.in_file(str(path)) from None


def write_binding(path: Path | str, binding: Binding):
    """Save `binding` at `path` (atomically, in the canonical form)."""
    write_file(path, binding.to_json())


def load_binding(data: Any, key: str = '') -> Binding:
    """A Binding from JSON data (already parsed). Raises BindingError."""
    reader = ObjectReader(upgrade(data, VERSION, error=BindingError), error=BindingError)
    reader.required('version', int)
    name = reader.required('name', str)
    comment = reader.optional('comment', str, '')
    profile, mode = reader.required('profile', str), reader.required('mode', str)
    layers = reader.optional('layers', dict, {DEFAULT_LAYER: 0})
    base = reader.optional('base', dict, {})
    for channel, value in base.items():
        check_type(value, int, join_where('base', channel), BindingError)
    extras = tuple(_read_extra(item) for item in reader.each('extras', required=False))
    mappings = tuple(read_spec(item) for item in reader.each('mappings'))
    patterns_reader = reader.child('patterns', required=False)
    patterns = None if patterns_reader is None else PatternLibrary.from_json(patterns_reader)
    reader.finish()
    return Binding(name, profile, mode, mappings, layers, base, extras, patterns, comment, key)


def _read_extra(reader: ObjectReader) -> Attribute:
    name, kind = reader.required('name', str), reader.required('kind', str)
    options = reader.optional('options', list, [])
    for i, option in enumerate(options):
        check_type(option, str, join_where(reader.path('options'), f'[{i}]'), BindingError)
    layered = reader.optional('layered', bool, True)
    description = reader.optional('description', str, '')
    reader.finish()
    try:
        return make_extra(name, kind, description, options, layered)
    except ValueError as e:
        raise reader.fail(str(e)) from None


def _extra_json(extra: Attribute) -> dict:
    data: dict[str, Any] = {'name': extra.name, 'kind': str(extra.kind)}
    if extra.options:
        data['options'] = list(extra.options)
    if not extra.layered:
        data['layered'] = False
    if extra.description:
        data['description'] = extra.description
    return data


# ── Resolving ───────────────────────────────────────────────────────────────

@dataclass(frozen=True, eq=False)
class ResolvedBinding:
    """A binding checked against its profile: the fixture's attributes and
    the mappings to render with, in priority order (patterns first). Their
    channel names are layer a's; channel() gives another layer's."""

    binding:    Binding
    profile:    Profile
    mode:       Mode
    attributes: AttributeSet
    mappings:   tuple[AttributeMapping, ...]
    layered:    tuple[bool, ...]          # per mapping: once per layer, or once for the whole fixture

    @property
    def layers(self) -> tuple[str, ...]:
        return tuple(self.binding.layers)

    def channel(self, name: str, layer: str = DEFAULT_LAYER) -> str:
        """The channel that layer a's channel `name` is on `layer`."""
        key = _shift(self.mode, self.binding.layers, name, layer)
        if key is None:
            raise KeyError(f'"{name}" has no channel on layer {layer}')
        return key


def _shift(mode: Mode, layers: Mapping[str, int], name: str, layer: str) -> str | None:
    """Layer a's channel `name` on `layer`, or None if the mode has nothing there."""
    index = mode.offset(name) + layers[layer]
    return mode.channels[index] if index < mode.footprint else None


def _check_value(channel: Channel, value: int, off: bool, where: str = ''):
    """The safety rules for sending `value` on `channel` (`off`: it means "off")."""
    segment = channel.capability_at(value)
    if segment is None:
        raise BindingError(f'{value} on "{channel.key}" isn\'t described by the profile', where)
    span = f'{segment.start}–{segment.end}'
    if segment.type == 'Maintenance':
        raise BindingError(f'{value} on "{channel.key}" is in a Maintenance segment ({span}), which PyLZR '
                           'never sends', where)
    if segment.type == 'NoFunction' and not off:
        raise BindingError(f'{value} on "{channel.key}" is in a NoFunction segment ({span}); only an off '
                           'or zero value may be', where)


class _Layout:
    """The mode's channels and how layers shift them, for checking."""

    def __init__(self, binding: Binding, mode: Mode, channels: Mapping[str, Channel]):
        self.layers, self.mode, self.channels = binding.layers, mode, channels

    def on_layer(self, name: str, layer: str, where: str = '') -> Channel:
        key = _shift(self.mode, self.layers, name, layer)
        if key is None:
            index = self.mode.offset(name) + self.layers[layer]
            raise BindingError(f'"{name}" has no channel on layer {layer}: the mode has nothing at channel '
                               f'{index + 1} (check "layers")', where)
        return self.channels[key]

    def check(self, mapping: AttributeMapping, layered: bool):
        """Every value the mapping could send is safe on every layer it's
        used on, and layer a's segments repeat on the others."""
        off = mapping.off_values()
        for name, values in mapping.outputs().items():
            for layer in (self.layers if layered else (DEFAULT_LAYER,)):
                channel = self.on_layer(name, layer)
                if _segments(channel) != _segments(self.channels[name]):
                    raise BindingError(f'"{channel.key}" (layer {layer}) has different segments from "{name}" '
                                       '(check "layers")')
                for value in sorted(values):
                    _check_value(channel, value, value in off.get(name, ()))


def _segments(channel: Channel) -> list[tuple[int, int, str]]:
    return [(c.start, c.end, c.type) for c in channel.capabilities]


def _check_attributes(mapping: AttributeMapping, attributes: AttributeSet) -> bool:
    """The mapping's attributes exist, with the right kinds and choices. True
    if they're per layer, False if they belong to the whole fixture."""
    for name, kind in mapping.kinds.items():
        try:
            attribute = attributes[name]
        except KeyError as e:
            raise BindingError(e.args[0]) from None
        if attribute.kind != kind:
            raise BindingError(f'"{name}" is a {attribute.kind} attribute; a {type(mapping).__name__.lower()} '
                               f'mapping needs a {kind} one here')
    for name, choices in mapping.options().items():
        known = attributes[name].options
        unknown = sorted(choices - set(known))
        if unknown:
            raise BindingError(f'{name} has no choice "{unknown[0]}" (it has: {", ".join(known)})')
    layered = {attributes[name].layered for name in mapping.kinds}
    if len(layered) > 1:
        raise BindingError('mixes attributes of the whole fixture (like power) with per-layer ones')
    return layered.pop()


def _check_patterns(library: PatternLibrary, layout: _Layout) -> PatternMapping:
    for i, name in enumerate(library.channels):
        find_channel(layout.channels, name, f'patterns.channels[{i}]')
    for layer in layout.layers:
        for name, value in library.none.items():
            where = f'patterns.none.{name}'
            _check_value(layout.on_layer(name, layer, where), value, True, where)
        for i, entry in enumerate(library.entries):
            for name, value in entry.values.items():
                where = f'patterns.library[{i}].values.{name}'
                _check_value(layout.on_layer(name, layer, where), value, False, where)
    return PatternMapping(library)


def _resolve(binding: Binding, profile: Profile) -> ResolvedBinding:
    if profile.key and profile.key != binding.profile:
        raise BindingError(f'is for the profile "{binding.profile}", not "{profile.key}"', 'profile')
    try:
        mode = profile.mode(binding.mode)
    except KeyError as e:
        raise BindingError(e.args[0], 'mode') from None
    channels = {key: profile.channels[key] for key in mode.channels if key is not None}
    layout = _Layout(binding, mode, channels)
    attributes = AttributeSet(binding.extras)

    for name, value in binding.base.items():
        where = join_where('base', name)
        _check_value(find_channel(channels, name, where), value, True, where)

    mappings: list[AttributeMapping] = []
    layered: list[bool] = []
    pattern_channels: tuple[str, ...] = ()
    if binding.patterns is not None:
        mappings.append(_check_patterns(binding.patterns, layout))
        layered.append(True)
        pattern_channels = binding.patterns.channels

    for i, spec in enumerate(binding.mappings):
        try:
            mapping = spec.build(channels)
            per_layer = _check_attributes(mapping, attributes)
            for name in mapping.channels:
                if name in pattern_channels:
                    raise BindingError(f'"{name}" is a pattern channel (see "patterns")')
            layout.check(mapping, per_layer)
        except BindingError as e:
            raise e.within(f'mappings[{i}]') from None
        mappings.append(mapping)
        layered.append(per_layer)

    used = {name for mapping in mappings for name in mapping.attributes}
    for i, extra in enumerate(binding.extras):
        if extra.name not in used:
            raise BindingError(f'"{extra.name}" isn\'t used by any mapping', f'extras[{i}]')
    return ResolvedBinding(binding, profile, mode, attributes, tuple(mappings), tuple(layered))
