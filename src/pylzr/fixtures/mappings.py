"""Mapping types: how attribute values become DMX values on a fixture's
channels. Each type is one small class for one way a channel can be cut up:

  Linear     a gradient segment, 0..1 → one end to the other        (size, scan speed, strobe)
  Bipolar    a gradient segment with a centre, -1..1                (position)
  Direction  forward and reverse segments, each slow → fast, ±      (spin, colour speed)
  Options    discrete values: each choice sets one or more channels (power, colour)
  Selected   an option picks which inner mapping is used            (draw style picks the scan segment)

They work in plain DMX numbers, layer-free attribute names and channel keys;
which segment of which channel a mapping uses comes from the fixture's
binding (binding.py), which also checks the numbers against its profile.
Every type can list all the DMX values it could ever send (outputs()), so a
binding's safety rules are checked exhaustively, not by sampling.

A mapping is *active* when it has something to say, and then claims its
channels; when several mappings share a channel (a static angle and a spin,
say) the renderer gives it to the first active one. A motion with no "off"
value is inactive at 0, which hands the channel back to the static setting;
a Linear mapping can do the same (release_at_zero: wave_x at 0 lets wave_y
have a shared wave channel).

off_values() are the values a mapping sends to mean "off" or "nothing" (a
strobe's zero, a speed's off, a choice called off or none): the only values
a binding may send on a profile's NoFunction segments.
"""

import math
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from .attributes import NAME_RE, Kind

DMX_MAX = 255

OFF_CHOICES = ('off', 'none')       # option choices that mean "nothing"

Values = Mapping[str, Any]          # attribute name → validated value, for one layer
Outputs = dict[str, frozenset[int]] # channel → DMX values


def dmx_round(value: float) -> int:
    """Round half up, the same on every platform (Python's round() rounds half to even)."""
    return math.floor(value + 0.5)


def _check_dmx(value: Any, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= DMX_MAX:
        raise ValueError(f'{what} must be a DMX value 0–{DMX_MAX}, not {value!r}')
    return value


def _check_name(name: Any, what: str) -> str:
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise ValueError(f'{what} "{name}" is not an attribute name')
    return name


def _check_fraction(value: Any, what: str, low: float = 0.0, high: float = 1.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ValueError(f'{what} must be a number from {low:g} to {high:g}, not {value!r}')
    return float(value)


def _span(start: int, end: int) -> frozenset[int]:
    """Every DMX value from start to end, whichever is larger."""
    return frozenset(range(min(start, end), max(start, end) + 1))


def _merge(*parts: Mapping[str, frozenset]) -> dict[str, frozenset]:
    """Per-key unions, keys in first-seen order."""
    merged: dict[str, frozenset] = {}
    for part in parts:
        for key, values in part.items():
            merged[key] = merged.get(key, frozenset()) | values
    return merged


class AttributeMapping(ABC):
    """What every mapping type offers."""

    @property
    @abstractmethod
    def kinds(self) -> dict[str, Kind]:
        """The attributes it reads, and the kind each must be."""

    @property
    def attributes(self) -> tuple[str, ...]:
        return tuple(self.kinds)

    @property
    @abstractmethod
    def channels(self) -> tuple[str, ...]:
        """The channels it can write."""

    @abstractmethod
    def active(self, values: Values) -> bool:
        """True if it has something to send for these attribute values."""

    @abstractmethod
    def render(self, values: Values) -> dict[str, int]:
        """The DMX value for each of its channels (call only when active)."""

    @abstractmethod
    def outputs(self) -> Outputs:
        """Every DMX value it could ever send, per channel."""

    def off_values(self) -> Outputs:
        """The values among outputs() that mean "off" or "nothing", per channel."""
        return {}

    def options(self) -> dict[str, frozenset[str]]:
        """The choices it reads from each option attribute."""
        return {}


@dataclass(frozen=True)
class Linear(AttributeMapping):
    """A continuous attribute (0..1) across a gradient segment: 0 sends
    `start`, 1 sends `end` (either may be the larger, e.g. a size channel
    running large → small). Calibration: min/max say which part of the
    attribute's range this fixture uses (0.1 / 0.9: never the extremes).

    An attribute of exactly 0 can instead send `zero` (strobe 0 = off), or,
    with release_at_zero, send nothing: the mapping is then inactive, so
    another mapping can have the channel (wave_x 0 lets wave_y use it)."""

    attribute:       str
    channel:         str
    start:           int
    end:             int
    min:             float = 0.0
    max:             float = 1.0
    zero:            int | None = None
    release_at_zero: bool = False

    def __post_init__(self):
        _check_name(self.attribute, 'attribute')
        _check_dmx(self.start, 'start')
        _check_dmx(self.end, 'end')
        _check_fraction(self.min, 'min')
        _check_fraction(self.max, 'max')
        if self.min > self.max:
            raise ValueError(f'min ({self.min:g}) is above max ({self.max:g})')
        if self.zero is not None:
            _check_dmx(self.zero, 'zero')
            if self.release_at_zero:
                raise ValueError('at 0 it either sends zero or releases the channel, not both')

    @property
    def kinds(self) -> dict[str, Kind]:
        return {self.attribute: Kind.CONTINUOUS}

    @property
    def channels(self) -> tuple[str, ...]:
        return (self.channel,)

    def active(self, values: Values) -> bool:
        return self.attribute in values and not (self.release_at_zero and values[self.attribute] == 0)

    def _at(self, fraction: float) -> int:
        return dmx_round(self.start + fraction * (self.end - self.start))

    def render(self, values: Values) -> dict[str, int]:
        value = values[self.attribute]
        if value == 0 and self.zero is not None:
            return {self.channel: self.zero}
        return {self.channel: self._at(self.min + value * (self.max - self.min))}

    def outputs(self) -> Outputs:
        values = _span(self._at(self.min), self._at(self.max))
        return {self.channel: values | self._zero()}

    def off_values(self) -> Outputs:
        return {self.channel: self._zero()} if self.zero is not None else {}

    def _zero(self) -> frozenset[int]:
        return frozenset() if self.zero is None else frozenset({self.zero})


@dataclass(frozen=True)
class Bipolar(AttributeMapping):
    """A bipolar attribute (-1..1) across a gradient segment with a centre:
    -1 sends `low`, 0 `centre`, +1 `high`. Each half is scaled on its own,
    so an off-centre centre (128 in 0–255) is still exact. `limit` keeps it
    inside part of each half (0.6: never past 60 % of the way to the edge,
    e.g. to keep a beam on-screen)."""

    attribute: str
    channel:   str
    low:       int
    centre:    int
    high:      int
    limit:     float = 1.0

    def __post_init__(self):
        _check_name(self.attribute, 'attribute')
        for name in ('low', 'centre', 'high'):
            _check_dmx(getattr(self, name), name)
        if not min(self.low, self.high) <= self.centre <= max(self.low, self.high):
            raise ValueError(f'centre ({self.centre}) must lie between low ({self.low}) and high ({self.high})')
        if isinstance(self.limit, bool) or not isinstance(self.limit, (int, float)) or not 0 < self.limit <= 1:
            raise ValueError(f'limit must be above 0 and at most 1, not {self.limit!r}')

    @property
    def kinds(self) -> dict[str, Kind]:
        return {self.attribute: Kind.BIPOLAR}

    @property
    def channels(self) -> tuple[str, ...]:
        return (self.channel,)

    def active(self, values: Values) -> bool:
        return self.attribute in values

    def _at(self, value: float) -> int:
        edge = self.high if value >= 0 else self.low
        return dmx_round(self.centre + abs(value) * self.limit * (edge - self.centre))

    def render(self, values: Values) -> dict[str, int]:
        return {self.channel: self._at(values[self.attribute])}

    def outputs(self) -> Outputs:
        return {self.channel: _span(self._at(-1), self._at(1))}


@dataclass(frozen=True)
class Direction(AttributeMapping):
    """A bipolar speed over two segments: + runs through `forward`, − through
    `reverse`, each given as (slow, fast) DMX values, and the further from 0
    the faster. At 0 (or within the deadband) it sends `off`; with no `off`
    it's inactive there, so another mapping can use the channel (a spin at 0
    hands the channel back to the static angle)."""

    attribute: str
    channel:   str
    forward:   tuple[int, int]
    reverse:   tuple[int, int]
    off:       int | None = None
    deadband:  float = 0.0

    def __post_init__(self):
        _check_name(self.attribute, 'attribute')
        for name in ('forward', 'reverse'):
            pair = getattr(self, name)
            if not isinstance(pair, (tuple, list)) or len(pair) != 2:
                raise ValueError(f'{name} must be (slow, fast) DMX values, not {pair!r}')
            for end in pair:
                _check_dmx(end, name)
            object.__setattr__(self, name, tuple(pair))
        if self.off is not None:
            _check_dmx(self.off, 'off')
        _check_fraction(self.deadband, 'deadband', 0.0, 0.99)

    @property
    def kinds(self) -> dict[str, Kind]:
        return {self.attribute: Kind.BIPOLAR}

    @property
    def channels(self) -> tuple[str, ...]:
        return (self.channel,)

    def _moving(self, value: float) -> bool:
        return abs(value) > self.deadband

    def active(self, values: Values) -> bool:
        return self.attribute in values and (self.off is not None or self._moving(values[self.attribute]))

    def render(self, values: Values) -> dict[str, int]:
        value = values[self.attribute]
        if not self._moving(value):
            return {self.channel: self.off}
        slow, fast = self.forward if value > 0 else self.reverse
        speed = (abs(value) - self.deadband) / (1 - self.deadband)
        return {self.channel: dmx_round(slow + speed * (fast - slow))}

    def outputs(self) -> Outputs:
        return {self.channel: _span(*self.forward) | _span(*self.reverse) | self._off()}

    def off_values(self) -> Outputs:
        return {self.channel: self._off()} if self.off is not None else {}

    def _off(self) -> frozenset[int]:
        return frozenset() if self.off is None else frozenset({self.off})


@dataclass(frozen=True)
class Options(AttributeMapping):
    """An option attribute: each choice sets fixed values on one or more
    channels (a pattern group *and* number, say). A choice the fixture
    doesn't have isn't in `values`; it's then inactive, i.e. ignored."""

    attribute: str
    values:    Mapping[str, Mapping[str, int]]

    def __post_init__(self):
        _check_name(self.attribute, 'attribute')
        if not self.values:
            raise ValueError(f'"{self.attribute}" needs at least one choice')
        frozen = {}
        for option, settings in self.values.items():
            _check_name(option, 'choice')
            if not settings:
                raise ValueError(f'choice "{option}" sets no channel')
            frozen[option] = MappingProxyType({ch: _check_dmx(v, f'{option} on "{ch}"') for ch, v in settings.items()})
        object.__setattr__(self, 'values', MappingProxyType(frozen))

    @property
    def kinds(self) -> dict[str, Kind]:
        return {self.attribute: Kind.OPTION}

    @property
    def channels(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(ch for settings in self.values.values() for ch in settings))

    def active(self, values: Values) -> bool:
        return values.get(self.attribute) in self.values

    def render(self, values: Values) -> dict[str, int]:
        return dict(self.values[values[self.attribute]])

    def outputs(self) -> Outputs:
        return self._sent(self.values)

    def off_values(self) -> Outputs:
        return self._sent({option: s for option, s in self.values.items() if option in OFF_CHOICES})

    def options(self) -> dict[str, frozenset[str]]:
        return {self.attribute: frozenset(self.values)}

    @staticmethod
    def _sent(choices: Mapping[str, Mapping[str, int]]) -> Outputs:
        return _merge(*({ch: frozenset({value}) for ch, value in s.items()} for s in choices.values()))


@dataclass(frozen=True)
class Selected(AttributeMapping):
    """An option attribute (the selector) picks which inner mapping is used:
    e.g. draw_style 'line' or 'dots' picks the line-scan or dot-scan segment
    for scan_speed. With the selector unset, `default` is used; a choice
    without an inner mapping makes it inactive (ignored)."""

    selector: str
    choices:  Mapping[str, AttributeMapping]
    default:  str

    def __post_init__(self):
        _check_name(self.selector, 'selector')
        if not self.choices:
            raise ValueError(f'selector "{self.selector}" needs at least one choice')
        for option, inner in self.choices.items():
            _check_name(option, 'choice')
            if not isinstance(inner, AttributeMapping):
                raise ValueError(f'choice "{option}" must be a mapping, not {inner!r}')
            if self.selector in inner.attributes:
                raise ValueError(f'choice "{option}" reads its own selector "{self.selector}"')
        if self.default not in self.choices:
            raise ValueError(f'default "{self.default}" is not one of the choices ({", ".join(self.choices)})')
        object.__setattr__(self, 'choices', MappingProxyType(dict(self.choices)))

    @property
    def kinds(self) -> dict[str, Kind]:
        kinds = {self.selector: Kind.OPTION}
        for inner in self.choices.values():
            kinds.update(inner.kinds)
        return kinds

    @property
    def channels(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(ch for inner in self.choices.values() for ch in inner.channels))

    def chosen(self, values: Values) -> AttributeMapping | None:
        """The inner mapping these values select (None: a choice it doesn't have)."""
        return self.choices.get(values.get(self.selector, self.default))

    def active(self, values: Values) -> bool:
        inner = self.chosen(values)
        return inner is not None and inner.active(values)

    def render(self, values: Values) -> dict[str, int]:
        return self.chosen(values).render(values)

    def outputs(self) -> Outputs:
        return _merge(*(inner.outputs() for inner in self.choices.values()))

    def off_values(self) -> Outputs:
        return _merge(*(inner.off_values() for inner in self.choices.values()))

    def options(self) -> dict[str, frozenset[str]]:
        return _merge({self.selector: frozenset(self.choices)}, *(inner.options() for inner in self.choices.values()))
