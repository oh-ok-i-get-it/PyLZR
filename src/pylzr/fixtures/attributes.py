"""The attribute vocabulary: fixture-independent controls such as size, pos_x
or color. Everything creative (scenes, sound-reactive mappings, shows, the
ML model) speaks only in attributes; a fixture's binding turns them into DMX
values, so the same content works on any laser.

Kinds of value:
  continuous  0..1               e.g. size (0 smallest … 1 largest)
  bipolar     -1..1, 0 = centre  e.g. pos_x, spin_z (− anticlockwise … + clockwise)
  option      one named choice   e.g. color 'red', draw_style 'dots'
  pattern     a PatternRequest   matched in the fixture's pattern library
  event       momentary (True)   e.g. blackout (used by scenes, a later phase)

A laser with several pattern outputs has its attributes once per layer
('a', 'b', …): AttrKey('size', 'b'), written 'size@b'. Plain 'size' means
'size@a', so one-layer lasers never deal with layers. A few attributes
belong to the whole fixture (layered=False), e.g. power.

CORE is what every binding speaks. A binding can add extras for unusual
features; their names start with 'x_' so they never clash with core names
added later.
"""

import difflib
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any

NAME_RE       = re.compile(r'[a-z][a-z0-9_]*\Z')   # attribute and option names
LAYER_RE      = re.compile(r'[a-z]\Z')             # layers are single letters: a, b, …
DEFAULT_LAYER = 'a'
EXTRA_PREFIX  = 'x_'


class Kind(StrEnum):
    CONTINUOUS = 'continuous'
    BIPOLAR    = 'bipolar'
    OPTION     = 'option'
    PATTERN    = 'pattern'
    EVENT      = 'event'


def _number(value: Any, low: float, high: float, name: str) -> float:
    # NaN fails the range comparison, so it's rejected too
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ValueError(f'{name} must be a number from {low:g} to {high:g}, not {value!r}')
    return float(value)


@dataclass(frozen=True)
class PatternRequest:
    """Which pattern to show. Either a category plus any scales (each 0..1,
    e.g. energy 0.8), matched against the fixture's pattern library, or one
    library entry by name. Make one with PatternRequest.of('tunnel',
    energy=0.8) or PatternRequest.entry('tunnel 3')."""

    category: str = ''
    scales:   tuple[tuple[str, float], ...] = ()    # (scale, value), sorted by scale
    name:     str = ''

    def __post_init__(self):
        if bool(self.category) == bool(self.name):
            raise ValueError('a pattern request needs a category or an entry name (not both)')
        if self.name and self.scales:
            raise ValueError('scales only go with a category')
        checked = {}
        for scale, value in self.scales:
            if not isinstance(scale, str) or not NAME_RE.match(scale):
                raise ValueError(f'"{scale}" is not a scale name')
            if scale in checked:
                raise ValueError(f'scale "{scale}" is given twice')
            checked[scale] = _number(value, 0, 1, f'scale "{scale}"')
        object.__setattr__(self, 'scales', tuple(sorted(checked.items())))

    @classmethod
    def of(cls, category: str, **scales: float) -> 'PatternRequest':
        return cls(category=category, scales=tuple(scales.items()))

    @classmethod
    def entry(cls, name: str) -> 'PatternRequest':
        return cls(name=name)

    @property
    def scale_values(self) -> dict[str, float]:
        return dict(self.scales)


@dataclass(frozen=True)
class Attribute:
    """One attribute: its name, kind, a one-line description (shown as a
    tooltip), its choices if it's an option, and whether it exists once per
    layer (layered) or once per fixture."""

    name:        str
    kind:        Kind
    description: str
    options:     tuple[str, ...] = ()
    layered:     bool = True

    def __post_init__(self):
        if not NAME_RE.match(self.name):
            raise ValueError(f'"{self.name}" is not an attribute name (lowercase letters, digits and _)')
        object.__setattr__(self, 'kind', Kind(self.kind))
        if self.kind == Kind.OPTION:
            if not self.options:
                raise ValueError(f'option attribute "{self.name}" needs its options')
            for option in self.options:
                if not isinstance(option, str) or not NAME_RE.match(option):
                    raise ValueError(f'"{option}" is not an option name for "{self.name}"')
            if len(set(self.options)) != len(self.options):
                raise ValueError(f'"{self.name}" lists an option twice')
            object.__setattr__(self, 'options', tuple(self.options))
        elif self.options:
            raise ValueError(f'only option attributes have options ("{self.name}" is {self.kind})')

    @property
    def is_extra(self) -> bool:
        return self.name.startswith(EXTRA_PREFIX)

    def validate(self, value: Any) -> Any:
        """`value` if it suits this attribute (numbers as float), else ValueError."""
        if self.kind == Kind.CONTINUOUS:
            return _number(value, 0, 1, self.name)
        if self.kind == Kind.BIPOLAR:
            return _number(value, -1, 1, self.name)
        if self.kind == Kind.OPTION:
            if value not in self.options:
                raise ValueError(f'{self.name} must be one of {", ".join(self.options)}, not {value!r}')
            return value
        if self.kind == Kind.PATTERN:
            if not isinstance(value, PatternRequest):
                raise ValueError(f'{self.name} must be a PatternRequest, not {value!r}')
            return value
        if value is not True:
            raise ValueError(f'{self.name} is an event: its value is True, not {value!r}')
        return value


def make_extra(name: str, kind: Kind | str, description: str = '', options: Iterable[str] = (),
               layered: bool = True) -> Attribute:
    """A binding's own attribute. Its name must start with 'x_'."""
    if not name.startswith(EXTRA_PREFIX) or len(name) == len(EXTRA_PREFIX):
        raise ValueError(f'extra attribute "{name}" must be named x_<something>')
    try:
        kind = Kind(kind)
    except ValueError:
        raise ValueError(f'"{kind}" is not a kind of attribute ({", ".join(Kind)})') from None
    return Attribute(name, kind, description, tuple(options), layered)


@dataclass(frozen=True, order=True)
class AttrKey:
    """An attribute on one layer, written 'size@b'; 'size' is layer 'a'."""

    name:  str
    layer: str = DEFAULT_LAYER

    def __post_init__(self):
        if not isinstance(self.name, str) or not NAME_RE.match(self.name):
            raise ValueError(f'"{self.name}" is not an attribute name')
        if not isinstance(self.layer, str) or not LAYER_RE.match(self.layer):
            raise ValueError(f'"{self.layer}" is not a layer (a single letter: a, b, …)')

    @classmethod
    def parse(cls, text: 'str | AttrKey') -> 'AttrKey':
        if isinstance(text, AttrKey):
            return text
        name, at, layer = text.partition('@')
        return cls(name, layer) if at else cls(name)

    def __str__(self) -> str:
        return self.name if self.layer == DEFAULT_LAYER else f'{self.name}@{self.layer}'


# ── The core vocabulary ─────────────────────────────────────────────────────

COLORS = ('white', 'red', 'yellow', 'green', 'cyan', 'blue', 'magenta', 'original')

_C, _B, _O, _P, _E = Kind.CONTINUOUS, Kind.BIPOLAR, Kind.OPTION, Kind.PATTERN, Kind.EVENT

CORE_ATTRIBUTES: tuple[Attribute, ...] = (
    Attribute('power', _O, 'Laser output off or on', ('off', 'on'), layered=False),
    Attribute('pattern', _P, 'Which pattern: a category and scales, matched in the fixture\'s pattern '
                             'library. Unset: this layer shows no pattern'),
    Attribute('size', _C, 'Pattern size: 0 smallest … 1 largest'),
    Attribute('pos_x', _B, 'Horizontal position: −1 one side … 0 centre … +1 the other'),
    Attribute('pos_y', _B, 'Vertical position: −1 down … 0 centre … +1 up'),
    Attribute('color', _O, 'A fixed colour; "original" is the pattern\'s own colours', COLORS),
    Attribute('color_effect', _O, 'A colour-changing effect instead of a fixed colour',
              ('none', 'cycle', 'rgb_cycle', 'original_cycle', 'flow', 'gradient')),
    Attribute('flow_variant', _C, 'Which flowing-colour combination (0 first … 1 last), with color_effect flow'),
    Attribute('color_speed', _B, 'Speed of the colour effect: + forwards, − backwards, 0 still'),
    Attribute('draw_style', _O, 'How the pattern is drawn', ('bright_line', 'line', 'dots')),
    Attribute('scan_speed', _C, 'Drawing speed for the draw style: 0 slow … 1 fast'),
    Attribute('strobe', _C, 'Strobe speed: 0 off … 1 fastest'),
    Attribute('rot_x', _C, 'Static rotation around X: 0 … 1 = one full turn'),
    Attribute('rot_y', _C, 'Static rotation around Y: 0 … 1 = one full turn'),
    Attribute('rot_z', _C, 'Static rotation around Z: 0 … 1 = one full turn'),
    Attribute('spin_x', _B, 'Continuous rotation around X: + clockwise, − anticlockwise, 0 none'),
    Attribute('spin_y', _B, 'Continuous rotation around Y: + clockwise, − anticlockwise, 0 none'),
    Attribute('spin_z', _B, 'Continuous rotation around Z: + clockwise, − anticlockwise, 0 none'),
    Attribute('shift_x', _B, 'Static horizontal shift: −1 inner/left … 0 centre … +1 outer/right'),
    Attribute('shift_y', _B, 'Static vertical shift: −1 down … 0 centre … +1 up'),
    Attribute('move_x', _B, 'Continuous horizontal movement: + outwards/right, − inwards/left, 0 none'),
    Attribute('move_y', _B, 'Continuous vertical movement: + up, − down, 0 none'),
    Attribute('move_style', _O, 'Movement style: repeating edge to edge, or with a gap', ('wrap', 'gap')),
    Attribute('zoom', _C, 'Static zoom: 1 full size … 0 a dot'),
    Attribute('zoom_motion', _C, 'Speed of the zoom effect: 0 none … 1 fastest'),
    Attribute('zoom_style', _O, 'Zoom effect', ('shrink', 'grow', 'pulse', 'pulse_alt')),
    Attribute('gradient_speed', _C, 'Colour gradient speed: 0 off … 1 fastest'),
    Attribute('wave_axis', _O, 'Direction of the wave effect', ('x', 'y')),
    Attribute('wave_speed', _C, 'Wave effect speed: 0 off … 1 fastest'),
    Attribute('blackout', _E, 'Everything dark at once', layered=False),
)

CORE: Mapping[str, Attribute] = MappingProxyType({a.name: a for a in CORE_ATTRIBUTES})


class AttributeSet:
    """The attributes one fixture understands: the core list plus its
    binding's extras. Looks attributes up and validates attribute states."""

    def __init__(self, extras: Iterable[Attribute] = ()):
        self._all: dict[str, Attribute] = dict(CORE)
        for extra in extras:
            if not extra.is_extra:
                raise ValueError(f'extra attribute "{extra.name}" must be named x_<something>')
            if extra.name in self._all:
                raise ValueError(f'extra attribute "{extra.name}" is defined twice')
            self._all[extra.name] = extra

    def __iter__(self) -> Iterator[Attribute]:
        return iter(self._all.values())

    def __contains__(self, name: object) -> bool:
        return name in self._all

    def __getitem__(self, name: str) -> Attribute:
        """The attribute called `name`; KeyError with a 'did you mean' hint if unknown."""
        try:
            return self._all[name]
        except KeyError:
            close = difflib.get_close_matches(str(name), list(self._all), n=1)
            hint = f' (did you mean "{close[0]}"?)' if close else ''
            raise KeyError(f'unknown attribute "{name}"{hint}') from None

    def validate(self, key: 'AttrKey | str', value: Any) -> tuple[AttrKey, Any]:
        """(key, value) checked: a known attribute, a layer only if it's
        layered, and a value of the right kind."""
        key = AttrKey.parse(key)
        try:
            attribute = self[key.name]
        except KeyError as e:
            raise ValueError(e.args[0]) from None
        if not attribute.layered and key.layer != DEFAULT_LAYER:
            raise ValueError(f'{key.name} belongs to the whole fixture, so it has no layer ("{key}")')
        return key, attribute.validate(value)

    def validate_state(self, state: Mapping['AttrKey | str', Any]) -> dict[AttrKey, Any]:
        """A whole state ({'size': 0.5, 'pos_x@b': -0.2, …}) checked, with
        keys as AttrKeys. 'size' and 'size@a' together are an error."""
        checked: dict[AttrKey, Any] = {}
        for raw_key, value in state.items():
            key, value = self.validate(raw_key, value)
            if key in checked:
                raise ValueError(f'"{key}" is given twice')
            checked[key] = value
        return checked
