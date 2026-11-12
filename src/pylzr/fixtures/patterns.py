"""The pattern library: a fixture's patterns, tagged so that shows can ask for
"a tunnel, energy 4" instead of a pattern number.

An entry is the channel values that show one pattern, as many channels as
the fixture needs (the Gruolin: a group and a number; a simpler laser: one
channel), plus its tags: a category and ratings on any scales
(vocabulary.py). The library also says which channels patterns use and what
"no pattern" is (the Gruolin: number 0, which leaves that output dark).

Matching a request (attributes.PatternRequest):
  - by name: that entry
  - by category: the entry in that category closest on the scales the
    request names. A scale an entry isn't rated on counts as the middle
    (level 3); ties go to the earlier entry; no entry in the category: None

PatternMapping makes a library the binding's mapping for the `pattern`
attribute: unset or unmatched, it sends "no pattern".
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any

from .attributes import NAME_RE, Kind, PatternRequest
from .errors import BindingError, join_where
from .jsonio import ObjectReader, check_type
from .mappings import DMX_MAX, AttributeMapping, Outputs, Values
from .vocabulary import MAX_NAME, check_category, level_value

ATTRIBUTE = 'pattern'
UNRATED   = level_value(3)       # how a scale an entry isn't rated on counts when matching


def _dmx(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= DMX_MAX:
        raise BindingError(f'must be a DMX value 0–{DMX_MAX}, not {value!r}', where)
    return value


def _channel_values(values: Any, where: str) -> MappingProxyType:
    """{channel: DMX value}, checked and read-only."""
    if not isinstance(values, Mapping) or not values:
        raise BindingError('needs at least one channel value', where)
    for channel in values:
        if not isinstance(channel, str) or not channel:
            raise BindingError(f'{channel!r} is not a channel name', where)
    return MappingProxyType({ch: _dmx(v, join_where(where, ch)) for ch, v in values.items()})


def _read_values(reader: ObjectReader, key: str) -> dict[str, int]:
    """A {channel: whole number} object from a file (ranges are checked later)."""
    values = reader.required(key, dict)
    return {ch: check_type(v, int, join_where(reader.path(key), ch), BindingError) for ch, v in values.items()}


def clean_name(text: str) -> str:
    """An entry name as stored: trimmed, single spaces, case kept."""
    return ' '.join(text.split())


@dataclass(frozen=True)
class PatternEntry:
    """One pattern: the values that show it, its name and its tags."""

    name:     str
    values:   Mapping[str, int]                    # channel (layer a) → DMX value
    category: str
    scales:   Mapping[str, float] = field(default_factory=dict)   # scale → 0.2 … 1.0, e.g. {'energy': 0.8}

    def __post_init__(self):
        if not isinstance(self.name, str) or not clean_name(self.name) or len(clean_name(self.name)) > MAX_NAME:
            raise BindingError(f'a pattern needs a name of 1–{MAX_NAME} characters, not {self.name!r}', 'name')
        object.__setattr__(self, 'name', clean_name(self.name))
        object.__setattr__(self, 'values', _channel_values(self.values, 'values'))
        try:
            check_category(self.category)
        except ValueError as e:
            raise BindingError(str(e), 'category') from None
        scales = {}
        for scale, value in dict(self.scales).items():
            where = join_where('scales', str(scale))
            if not isinstance(scale, str) or len(scale) > MAX_NAME or not NAME_RE.match(scale):
                raise BindingError(f'"{scale}" is not a scale name', where)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value <= 1:
                raise BindingError(f'a rating must be above 0 and at most 1, not {value!r}', where)
            scales[scale] = float(value)
        object.__setattr__(self, 'scales', MappingProxyType(scales))

    def rating(self, scale: str) -> float:
        """Its rating on `scale` (0.2 … 1.0); the middle if it isn't rated on it."""
        return self.scales.get(scale, UNRATED)

    def to_json(self) -> dict:
        data: dict[str, Any] = {'name': self.name, 'values': dict(self.values), 'category': self.category}
        if self.scales:
            data['scales'] = dict(self.scales)
        return data

    @classmethod
    def from_json(cls, reader: ObjectReader) -> 'PatternEntry':
        name = reader.required('name', str)
        values = _read_values(reader, 'values')
        category = reader.required('category', str)
        scales = reader.optional('scales', dict, {})
        for scale, value in scales.items():
            check_type(value, float, join_where(reader.path('scales'), scale), BindingError)
        reader.finish()
        try:
            return cls(name, values, category, scales)
        except BindingError as e:
            raise e.within(reader.where) from None


def _milli(value: float) -> int:
    return round(value * 1000)      # compared in whole thousandths, so equal distances tie exactly


def _distance(entry: PatternEntry, wanted: Mapping[str, float]) -> int:
    return sum((_milli(entry.rating(scale)) - _milli(value)) ** 2 for scale, value in wanted.items())


@dataclass(frozen=True)
class PatternLibrary:
    """The channels patterns use, the values meaning "no pattern", and the
    tagged entries, in order. Names are unique (ignoring case), and so is
    each entry's combination of values."""

    channels: tuple[str, ...]
    none:     Mapping[str, int]
    entries:  tuple[PatternEntry, ...] = ()

    def __post_init__(self):
        channels = tuple(self.channels)
        if not channels or any(not isinstance(ch, str) or not ch for ch in channels):
            raise BindingError('needs the channel names patterns use', 'channels')
        if len(set(channels)) != len(channels):
            raise BindingError('lists a channel twice', 'channels')
        object.__setattr__(self, 'channels', channels)
        object.__setattr__(self, 'none', _channel_values(self.none, 'none'))
        for ch in self.none:
            if ch not in channels:
                raise BindingError(f'"{ch}" is not one of the pattern channels', join_where('none', ch))
        entries = tuple(self.entries)
        names: dict[str, str] = {}
        combos: dict[tuple, str] = {}
        for i, entry in enumerate(entries):
            where = f'library[{i}]'
            missing = [ch for ch in channels if ch not in entry.values]
            if missing:
                raise BindingError(f'sets no value for "{missing[0]}" (every pattern sets all of: '
                                   f'{", ".join(channels)})', join_where(where, 'values'))
            for ch in entry.values:
                if ch not in channels:
                    raise BindingError(f'"{ch}" is not one of the pattern channels',
                                       join_where(where, f'values.{ch}'))
            if all(entry.values[ch] == value for ch, value in self.none.items()):
                raise BindingError('these values mean "no pattern" (see "none")', join_where(where, 'values'))
            if entry.name.casefold() in names:
                raise BindingError(f'the name "{entry.name}" is already used', join_where(where, 'name'))
            combo = tuple(entry.values[ch] for ch in channels)
            if combo in combos:
                raise BindingError(f'the same pattern as "{combos[combo]}"', join_where(where, 'values'))
            names[entry.name.casefold()] = entry.name
            combos[combo] = entry.name
        object.__setattr__(self, 'entries', entries)

    # ── Looking things up ───────────────────────────────────────────────

    def entry(self, name: str) -> PatternEntry | None:
        """The entry called `name` (ignoring case and extra spaces)."""
        wanted = clean_name(name).casefold()
        return next((e for e in self.entries if e.name.casefold() == wanted), None)

    def find(self, values: Mapping[str, int]) -> PatternEntry | None:
        """The entry with exactly these values, e.g. to show a browsed pattern's tags."""
        return next((e for e in self.entries if dict(e.values) == dict(values)), None)

    def in_category(self, category: str) -> tuple[PatternEntry, ...]:
        return tuple(e for e in self.entries if e.category == category)

    def match(self, request: PatternRequest) -> PatternEntry | None:
        """The entry a request asks for, or None (see the module docstring)."""
        if request.name:
            return self.entry(request.name)
        candidates = self.in_category(request.category)
        if not candidates:
            return None
        wanted = request.scale_values
        return min(candidates, key=lambda entry: _distance(entry, wanted))   # min keeps the first of equals

    # ── Editing (each returns a new library) ────────────────────────────

    def with_entry(self, entry: PatternEntry, replacing: str | None = None) -> 'PatternLibrary':
        """This library with `entry` added at the end, or in place of the
        entry called `replacing`."""
        if replacing is None:
            return PatternLibrary(self.channels, self.none, self.entries + (entry,))
        old = self.entry(replacing)
        if old is None:
            raise KeyError(f'no pattern called "{replacing}"')
        return PatternLibrary(self.channels, self.none, tuple(entry if e is old else e for e in self.entries))

    def without(self, name: str) -> 'PatternLibrary':
        old = self.entry(name)
        if old is None:
            raise KeyError(f'no pattern called "{name}"')
        return PatternLibrary(self.channels, self.none, tuple(e for e in self.entries if e is not old))

    # ── The binding file's "patterns" section ───────────────────────────

    def to_json(self) -> dict:
        return {'channels': list(self.channels), 'none': dict(self.none),
                'library': [entry.to_json() for entry in self.entries]}

    @classmethod
    def from_json(cls, reader: ObjectReader) -> 'PatternLibrary':
        channels = reader.required('channels', list)
        for i, ch in enumerate(channels):
            check_type(ch, str, join_where(reader.path('channels'), f'[{i}]'), BindingError)
        none = _read_values(reader, 'none')
        entries = [PatternEntry.from_json(item) for item in reader.each('library', required=False)]
        reader.finish()
        try:
            return cls(tuple(channels), none, tuple(entries))
        except BindingError as e:
            raise e.within(reader.where) from None


def _union(parts: Iterable[Mapping[str, int]]) -> Outputs:
    found: dict[str, set[int]] = {}
    for values in parts:
        for ch, value in values.items():
            found.setdefault(ch, set()).add(value)
    return {ch: frozenset(values) for ch, values in found.items()}


@dataclass(frozen=True)
class PatternMapping(AttributeMapping):
    """The `pattern` attribute through a library. Always active: an unset
    or unmatched request sends the library's "no pattern" values."""

    library: PatternLibrary

    @property
    def kinds(self) -> dict[str, Kind]:
        return {ATTRIBUTE: Kind.PATTERN}

    @property
    def channels(self) -> tuple[str, ...]:
        return self.library.channels

    def chosen(self, values: Values) -> PatternEntry | None:
        """The entry these values ask for (None: unset, or nothing matches)."""
        request = values.get(ATTRIBUTE)
        return None if request is None else self.library.match(request)

    def active(self, values: Values) -> bool:
        return True

    def render(self, values: Values) -> dict[str, int]:
        entry = self.chosen(values)
        return dict(entry.values if entry is not None else self.library.none)

    def outputs(self) -> Outputs:
        return _union([self.library.none, *(entry.values for entry in self.library.entries)])

    def off_values(self) -> Outputs:
        return _union([self.library.none])
