"""Rendering: a whole attribute state → one fixture's channel values.

    renderer = compile_fixture(binding, profile)
    result = renderer.render({'power': 'on', 'size': 0.5, 'pos_x@b': -0.2})
    result.values          # bytes, one per channel of the fixture's mode (36 on the Gruolin)

Rendering is stateless: an attribute that isn't set leaves its channels at
the fixture's default (the binding's base value, else the profile's
defaultValue, else 0). The pattern attribute is the exception by design:
unset, it sends "no pattern".

Shared channels: mappings are tried in the binding's priority order (on
each layer); an active mapping writes each of its channels that no earlier
mapping has written. One whose channel was taken is reported as ignored
(e.g. rot_z while spin_z is moving).

Portability: content written for another laser just works here. Keys this
fixture can't use — another laser's x_ extras, a layer it doesn't have, a
choice none of its mappings offers (color_effect 'fade' on the Gruolin) —
are skipped and reported as unsupported, never an error. A wrong value for
an attribute it does have (size 2) is a bug in the caller: ValueError.

Raw patterns (testers and the pattern browser only): render() can also be
given a layer's pattern-channel values directly (raw_patterns), to look at
patterns nobody has tagged yet. Content never does this: it asks for
patterns by category and scales, which is what keeps it portable. Raw values
are checked like a binding's: on a capability the profile describes, never
Maintenance.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .attributes import DEFAULT_LAYER, AttrKey, AttributeSet, Kind
from .binding import Binding, ResolvedBinding, check_value
from .errors import BindingError
from .mappings import OFF_CHOICES, AttributeMapping
from .ofl import Capability, Profile
from .patterns import PatternEntry, PatternLibrary, PatternMapping

State = Mapping['AttrKey | str', Any]
RawPatterns = Mapping[str, Mapping[str, int]]      # layer → {pattern channel (layer a's name) → DMX value}


@dataclass(frozen=True)
class Segment:
    """A run of DMX values on a channel that does one thing, e.g. 16–31
    'Line patterns, folder 2'."""

    start: int
    end:   int
    label: str

    def contains(self, value: int) -> bool:
        return self.start <= value <= self.end


@dataclass(frozen=True)
class PatternChannel:
    """One pattern channel on one layer: the segments a raw pattern may set it to."""

    name:     str                      # layer a's channel name, e.g. 'Pattern Group'
    segments: tuple[Segment, ...]

    def allows(self, value: int) -> bool:
        return any(segment.contains(value) for segment in self.segments)


def _label(capability: Capability) -> str:
    """A short name for a segment: its effect name, else the first part of its
    comment, else its type."""
    name = capability.properties.get('effectName')
    if isinstance(name, str) and name:
        return name
    if capability.comment:
        return capability.comment.split(':')[0].strip()
    return capability.type


@dataclass(frozen=True)
class Render:
    """One rendered state. `unsupported` and `ignored` list keys of the
    state, in its order; `patterns` is what each layer's pattern request
    matched (None: unset or nothing matched)."""

    values:      bytes
    unsupported: tuple[AttrKey, ...] = ()
    ignored:     tuple[AttrKey, ...] = ()
    patterns:    Mapping[str, PatternEntry | None] = MappingProxyType({})


@dataclass(frozen=True)
class _Slot:
    """One mapping on one layer, with where its channels are in the footprint."""

    mapping: AttributeMapping
    layer:   str
    offsets: Mapping[str, int]       # layer a's channel name → 0-based offset on this layer


class Renderer:
    """A fixture type ready to render: its binding resolved against its
    profile, with every channel position worked out once."""

    def __init__(self, resolved: ResolvedBinding):
        self.resolved = resolved
        mode, base, channels = resolved.mode, resolved.binding.base, resolved.profile.channels
        self._defaults = bytes(0 if key is None else base.get(key, channels[key].default_value)
                               for key in mode.channels)
        slots = []
        for mapping, layered in zip(resolved.mappings, resolved.layered, strict=True):
            for layer in (resolved.layers if layered else (DEFAULT_LAYER,)):
                offsets = {name: mode.offset(resolved.channel(name, layer)) for name in mapping.channels}
                slots.append(_Slot(mapping, layer, MappingProxyType(offsets)))
        self._slots = tuple(slots)
        patterns = next((m for m in resolved.mappings if isinstance(m, PatternMapping)), None)
        self._library = None if patterns is None else patterns.library
        choices: dict[AttrKey, frozenset[str]] = {}
        for slot in slots:
            for name in slot.mapping.attributes:
                choices.setdefault(AttrKey(name, slot.layer), frozenset())
            for name, options in slot.mapping.options().items():
                key = AttrKey(name, slot.layer)
                choices[key] = choices[key] | options
        self._choices = MappingProxyType(choices)      # every key some mapping reads → choices offered

    # ── About the fixture ───────────────────────────────────────────────

    @property
    def key(self) -> str:
        """The fixture type, e.g. 'gruolin/rgb-beam-36ch'."""
        return self.resolved.binding.key

    @property
    def name(self) -> str:
        return self.resolved.binding.name

    @property
    def footprint(self) -> int:
        return self.resolved.mode.footprint

    @property
    def layers(self) -> tuple[str, ...]:
        return self.resolved.layers

    @property
    def attributes(self) -> AttributeSet:
        return self.resolved.attributes

    @property
    def defaults(self) -> bytes:
        """What every channel sends when nothing is set."""
        return self._defaults

    def supports(self, key: 'AttrKey | str') -> bool:
        """True if some mapping reads this attribute on this layer."""
        return AttrKey.parse(key) in self._choices

    def choices(self, key: 'AttrKey | str') -> frozenset[str]:
        """The choices of an option attribute this fixture has mappings for."""
        return self._choices.get(AttrKey.parse(key), frozenset())

    @property
    def library(self) -> PatternLibrary | None:
        """The fixture's pattern library (None if its binding has no patterns)."""
        return self._library

    def pattern_channels(self, layer: str = DEFAULT_LAYER) -> tuple[PatternChannel, ...]:
        """The pattern channels on `layer`, with the segments a raw pattern may
        use there (every described one except Maintenance). Empty if the
        binding has no patterns."""
        if self._library is None:
            return ()
        result = []
        for name in self._library.channels:
            channel = self.resolved.profile.channels[self.resolved.channel(name, layer)]
            segments = tuple(Segment(cap.start, cap.end, _label(cap)) for cap in channel.capabilities
                             if cap.type != 'Maintenance')
            result.append(PatternChannel(name, segments))
        return tuple(result)

    def _raw_values(self, raw_patterns: RawPatterns) -> dict[str, dict[str, int]]:
        """raw_patterns checked, each layer's values complete (missing
        channels: the library's "no pattern" value, else the channel's default)."""
        if raw_patterns and self._library is None:
            raise ValueError(f'{self.name} has no pattern channels')
        checked = {}
        for layer, values in raw_patterns.items():
            if layer not in self.layers:
                raise ValueError(f'{self.name} has no layer "{layer}"')
            unknown = [name for name in values if name not in self._library.channels]
            if unknown:
                raise ValueError(f'"{unknown[0]}" is not a pattern channel of {self.name} '
                                 f'({", ".join(self._library.channels)})')
            complete = {}
            for name in self._library.channels:
                key = self.resolved.channel(name, layer)
                default = self._defaults[self.resolved.mode.offset(key)]
                value = values.get(name, self._library.none.get(name, default))
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ValueError(f'"{name}" needs a DMX value, not {value!r}')
                try:
                    check_value(self.resolved.profile.channels[key], value, off=True)
                except BindingError as e:
                    raise ValueError(e.message) from None
                complete[name] = value
            checked[layer] = complete
        return checked

    # ── Rendering ───────────────────────────────────────────────────────

    def render(self, state: State, raw_patterns: RawPatterns = MappingProxyType({})) -> Render:
        """The channel values for `state`. `raw_patterns` (testers only, see
        the module docstring) sets layers' pattern channels directly; a
        pattern request on such a layer is then ignored."""
        raw = self._raw_values(raw_patterns)
        per_layer: dict[str, dict[str, Any]] = {layer: {} for layer in self.layers}
        used: list[AttrKey] = []
        unsupported: list[AttrKey] = []
        for raw_key, raw_value in state.items():
            key = AttrKey.parse(raw_key)
            if key in used or key in unsupported:
                raise ValueError(f'"{key}" is given twice')
            if key not in self._choices:
                unsupported.append(key)
                continue
            key, value = self.attributes.validate(key, raw_value)
            if (self.attributes[key.name].kind == Kind.OPTION and value not in self._choices[key]
                    and value not in OFF_CHOICES):
                unsupported.append(key)
                continue
            per_layer[key.layer][key.name] = value
            used.append(key)

        values = bytearray(self._defaults)
        claimed: set[int] = set()
        won: set[AttrKey] = set()
        lost: set[AttrKey] = set()
        patterns: dict[str, PatternEntry | None] = {}
        for slot in self._slots:
            layer_values = per_layer[slot.layer]
            if isinstance(slot.mapping, PatternMapping) and slot.layer in raw:
                patterns[slot.layer] = slot.mapping.library.find(raw[slot.layer])
                for channel, value in raw[slot.layer].items():   # patterns come first: nothing has claimed these
                    claimed.add(slot.offsets[channel])
                    values[slot.offsets[channel]] = value
                lost.add(AttrKey('pattern', slot.layer))         # a request on this layer loses to the raw values
                continue
            if isinstance(slot.mapping, PatternMapping):
                patterns[slot.layer] = slot.mapping.chosen(layer_values)
                rendered = slot.mapping.render(layer_values)
            elif slot.mapping.active(layer_values):
                rendered = slot.mapping.render(layer_values)
            else:
                continue
            beaten = False
            for channel, value in rendered.items():
                offset = slot.offsets[channel]
                if offset in claimed:
                    beaten = True
                else:
                    claimed.add(offset)
                    values[offset] = value
            keys = {AttrKey(name, slot.layer) for name in slot.mapping.attributes}
            (lost if beaten else won).update(keys)
        ignored = tuple(key for key in used if key in lost and key not in won)
        return Render(bytes(values), tuple(unsupported), ignored, MappingProxyType(patterns))


def compile_fixture(binding: Binding, profile: Profile) -> Renderer:
    """A renderer for `binding` on `profile` (BindingError if they don't fit)."""
    return Renderer(binding.resolve(profile))
