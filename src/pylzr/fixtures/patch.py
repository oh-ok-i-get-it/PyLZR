"""The patch: which fixtures are at which DMX addresses (patch.json).

    {"version": 1, "fixtures": [
      {"name": "Laser L", "type": "gruolin/rgb-beam-36ch", "address": 1},
      {"name": "Laser R", "type": "gruolin/rgb-beam-36ch", "address": 37}]}

A fixture's type is a binding's key; its address is its first channel
(1–512). Names are unique, ignoring case.

How many channels a fixture takes depends on its type, so the rules that
need that are reported as problems rather than refused when loading:
  - its type isn't available (e.g. a binding file was deleted or is broken)
  - it runs past channel 512
  - it overlaps a fixture listed before it
A fixture with a problem is kept, shown and skipped when rendering, never
silently dropped. A Rig is the patch together with the renderers for its
types: what the testers and (later) scenes render through.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import PatchError
from .jsonio import ObjectReader, read_file, upgrade, write_file
from .patterns import clean_name
from .renderer import Render, Renderer, State
from .vocabulary import MAX_NAME

VERSION  = 1
UNIVERSE = 512


@dataclass(frozen=True)
class PatchEntry:
    """One fixture: its name, type (a binding's key) and first channel."""

    name:    str
    type:    str
    address: int

    def __post_init__(self):
        if not isinstance(self.name, str) or not clean_name(self.name) or len(clean_name(self.name)) > MAX_NAME:
            raise PatchError(f'a fixture needs a name of 1–{MAX_NAME} characters, not {self.name!r}', 'name')
        object.__setattr__(self, 'name', clean_name(self.name))
        if not isinstance(self.type, str) or not self.type.strip():
            raise PatchError(f'needs a fixture type, not {self.type!r}', 'type')
        if isinstance(self.address, bool) or not isinstance(self.address, int) or not 1 <= self.address <= UNIVERSE:
            raise PatchError(f'must be a channel from 1 to {UNIVERSE}, not {self.address!r}', 'address')

    def last(self, footprint: int) -> int:
        """Its last channel, for a type `footprint` channels long."""
        return self.address + footprint - 1


@dataclass(frozen=True)
class PatchProblem:
    """Why one fixture can't be used (by name)."""

    name:    str
    message: str

    def __str__(self) -> str:
        return f'{self.name}: {self.message}'


@dataclass(frozen=True)
class Patch:
    """The patched fixtures, in the order they're listed."""

    entries: tuple[PatchEntry, ...] = ()

    def __post_init__(self):
        entries = tuple(self.entries)
        seen: dict[str, str] = {}
        for i, entry in enumerate(entries):
            if not isinstance(entry, PatchEntry):
                raise PatchError(f'must be a patch entry, not {entry!r}', f'fixtures[{i}]')
            if entry.name.casefold() in seen:
                raise PatchError(f'the name "{entry.name}" is already used', f'fixtures[{i}].name')
            seen[entry.name.casefold()] = entry.name
        object.__setattr__(self, 'entries', entries)

    def entry(self, name: str) -> PatchEntry | None:
        """The fixture called `name` (ignoring case and extra spaces)."""
        wanted = clean_name(name).casefold()
        return next((e for e in self.entries if e.name.casefold() == wanted), None)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(e.name for e in self.entries)

    # ── Editing (each returns a new patch) ──────────────────────────────

    def with_fixture(self, entry: PatchEntry) -> 'Patch':
        return Patch(self.entries + (entry,))

    def replaced(self, name: str, entry: PatchEntry) -> 'Patch':
        old = self._existing(name)
        return Patch(tuple(entry if e is old else e for e in self.entries))

    def without(self, name: str) -> 'Patch':
        old = self._existing(name)
        return Patch(tuple(e for e in self.entries if e is not old))

    def _existing(self, name: str) -> PatchEntry:
        entry = self.entry(name)
        if entry is None:
            raise KeyError(f'no fixture called "{name}"')
        return entry

    # ── Rules that need each type's footprint ───────────────────────────

    def problems(self, footprints: Mapping[str, int]) -> tuple[PatchProblem, ...]:
        """What's wrong with each fixture, given the footprint of every
        available type (a type not in `footprints` isn't available)."""
        problems = []
        placed: list[tuple[PatchEntry, int]] = []          # usable so far, with their last channel
        for entry in self.entries:
            if entry.type not in footprints:
                problems.append(PatchProblem(entry.name, f'its type "{entry.type}" isn\'t available'))
                continue
            last = entry.last(footprints[entry.type])
            if last > UNIVERSE:
                problems.append(PatchProblem(entry.name, f'needs channels {entry.address}–{last}, but a universe '
                                                         f'ends at {UNIVERSE}'))
                continue
            other = next(((o, o_last) for o, o_last in placed if entry.address <= o_last and o.address <= last), None)
            if other is not None:
                o, o_last = other
                problems.append(PatchProblem(entry.name, f'channels {entry.address}–{last} overlap {o.name} '
                                                         f'({o.address}–{o_last})'))
                continue
            placed.append((entry, last))
        return tuple(problems)

    def next_free_address(self, footprint: int, footprints: Mapping[str, int]) -> int | None:
        """The lowest address where `footprint` channels fit without
        overlapping any fixture (one of an unavailable type counts as one
        channel). None if there's no room."""
        taken = [(e.address, e.last(footprints.get(e.type, 1))) for e in self.entries]
        address = 1
        while address + footprint - 1 <= UNIVERSE:
            clash = [last for first, last in taken if first <= address + footprint - 1 and address <= last]
            if not clash:
                return address
            address = max(clash) + 1
        return None

    def next_name(self, base: str = 'Laser') -> str:
        """'<base> N' with the lowest N (from 1) no fixture is called, ignoring
        case: a name to suggest for a new fixture."""
        taken = {name.casefold() for name in self.names}
        n = 1
        while f'{base} {n}'.casefold() in taken:
            n += 1
        return f'{base} {n}'

    # ── patch.json ──────────────────────────────────────────────────────

    def to_json(self) -> dict:
        return {'version': VERSION,
                'fixtures': [{'name': e.name, 'type': e.type, 'address': e.address} for e in self.entries]}


def load_patch(data: Any) -> Patch:
    """A Patch from JSON data (already parsed). Raises PatchError."""
    reader = ObjectReader(upgrade(data, VERSION, error=PatchError), error=PatchError)
    reader.required('version', int)
    entries = []
    for item in reader.each('fixtures'):
        name, kind, address = item.required('name', str), item.required('type', str), item.required('address', int)
        item.finish()
        try:
            entries.append(PatchEntry(name, kind, address))
        except PatchError as e:
            raise e.within(item.where) from None
    reader.finish()
    return Patch(tuple(entries))


def read_patch(path: Path | str) -> Patch:
    """The patch in the file at `path`. Problems raise PatchError naming the file."""
    data = read_file(path, PatchError)
    try:
        return load_patch(data)
    except PatchError as e:
        raise e.in_file(str(path)) from None


def write_patch(path: Path | str, patch: Patch):
    """Save `patch` at `path` (atomically)."""
    write_file(path, patch.to_json())


# ── The rig: the patch plus what renders it ─────────────────────────────────

class Rig:
    """A patch with the renderers for its types. Fixtures with a problem
    are listed in `problems` and can't be rendered."""

    def __init__(self, patch: Patch, renderers: Mapping[str, Renderer]):
        self.patch = patch
        self._renderers = dict(renderers)
        self.problems = patch.problems({kind: r.footprint for kind, r in self._renderers.items()})
        broken = {problem.name for problem in self.problems}
        self.usable: tuple[str, ...] = tuple(name for name in patch.names if name not in broken)

    def _usable(self, name: str) -> PatchEntry:
        entry = self.patch.entry(name)
        if entry is None:
            raise KeyError(f'no fixture called "{name}"')
        if entry.name not in self.usable:
            problem = next(p for p in self.problems if p.name == entry.name)
            raise KeyError(f'{problem} (so it can\'t be used)')
        return entry

    def renderer(self, name: str) -> Renderer:
        return self._renderers[self._usable(name).type]

    def render_fixture(self, name: str, state: State) -> tuple[int, Render]:
        """(first channel, render) for one fixture: what the testers send
        with DMXOutput.set_test_values(start, render.values)."""
        entry = self._usable(name)
        return entry.address, self._renderers[entry.type].render(state)

    def render(self, states: Mapping[str, State]) -> dict[int, int]:
        """{DMX channel: value} for every usable fixture with a state; one
        with a problem is skipped (it's in `problems`), an unknown name is a
        KeyError."""
        channels: dict[int, int] = {}
        for name, state in states.items():
            entry = self.patch.entry(name)
            if entry is None:
                raise KeyError(f'no fixture called "{name}"')
            if entry.name not in self.usable:
                continue
            start, result = self.render_fixture(name, state)
            channels.update((start + i, value) for i, value in enumerate(result.values))
        return channels
