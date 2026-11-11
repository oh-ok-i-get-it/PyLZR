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
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .attributes import DEFAULT_LAYER, AttrKey, AttributeSet, Kind
from .binding import Binding, ResolvedBinding
from .mappings import OFF_CHOICES, AttributeMapping
from .ofl import Profile
from .patterns import PatternEntry, PatternMapping

State = Mapping['AttrKey | str', Any]


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

    # ── Rendering ───────────────────────────────────────────────────────

    def render(self, state: State) -> Render:
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
            if isinstance(slot.mapping, PatternMapping):
                patterns[slot.layer] = slot.mapping.chosen(layer_values)
            if not slot.mapping.active(layer_values):
                continue
            beaten = False
            for channel, value in slot.mapping.render(layer_values).items():
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
