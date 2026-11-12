"""The fixture library: every profile and binding PyLZR can use, from two
places, plus your patch and vocabulary.

  shipped   inside PyLZR (pylzr/fixtures/data), updated with PyLZR
  yours     your fixtures folder, next to PyLZR.ini:
              profiles/<maker>/<name>.json, bindings/<maker>/<name>.json,
              patch.json, vocabulary.json

A file's key is its path under profiles/ or bindings/ without ".json", e.g.
the binding 'gruolin/rgb-beam-36ch'. A file of yours with the same key as a
shipped one is used instead of it.

Saving never touches the shipped files: a binding you change (e.g. by
tagging patterns) is saved to your folder, where it then overrides the
shipped one, so a PyLZR update never overwrites your tags.

Nothing here is fatal. A file that can't be read or doesn't fit its profile
is listed in `problems` and left out (a shipped file of the same key is used
instead, if there is one); everything else keeps working. Saving over a file
of yours that couldn't be read first keeps it as "<name>.unreadable.json",
so a typo in your file is never lost by saving from the app.
"""

import os
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from importlib.resources import as_file, files
from importlib.resources.abc import Traversable
from pathlib import Path
from types import MappingProxyType

from .binding import Binding, read_binding, write_binding
from .errors import BindingError, FixtureError
from .jsonio import read_file, write_file
from .ofl import Profile, read_profile
from .patch import Patch, Rig, read_patch, write_patch
from .renderer import Renderer
from .vocabulary import Vocabulary

PATCH_FILE      = 'patch.json'
VOCABULARY_FILE = 'vocabulary.json'
SHIPPED, YOURS  = 'shipped', 'yours'


def shipped_data() -> Traversable:
    """PyLZR's own fixture files."""
    return files('pylzr.fixtures').joinpath('data')


@dataclass(frozen=True)
class _Candidate:
    """One file for a key, read or not."""

    source: str                    # SHIPPED or YOURS
    label:  str                    # e.g. 'bindings/gruolin/rgb-beam-36ch.json (shipped)'
    path:   Path | None            # yours only: the file, in case it must be set aside
    value:  object
    error:  FixtureError | None


@dataclass(frozen=True)
class Problem:
    """A file that couldn't be used, and why."""

    file:    str
    message: str

    def __str__(self) -> str:
        return f'{self.file}: {self.message}' if self.file else self.message


def _json_files(folder: Traversable, prefix: str = '') -> Iterator[tuple[str, Traversable]]:
    """(key, file) for every .json file under `folder`, sorted, skipping hidden ones."""
    if not folder.is_dir():
        return
    for item in sorted(folder.iterdir(), key=lambda i: i.name):
        if item.name.startswith('.'):
            continue
        if item.is_dir():
            yield from _json_files(item, f'{prefix}{item.name}/')
        elif item.name.endswith('.json') and '.unreadable' not in item.name:
            yield prefix + item.name.removesuffix('.json'), item


def _set_aside(path: Path) -> Path:
    """Rename an unreadable file to <name>.unreadable.json (numbered if taken)."""
    stem = path.name.removesuffix('.json')
    target, n = path.with_name(f'{stem}.unreadable.json'), 1
    while target.exists():
        n += 1
        target = path.with_name(f'{stem}.unreadable-{n}.json')
    os.replace(path, target)
    return target


class FixtureLibrary:
    """Everything fixture-related PyLZR loads. `folder` is your fixtures
    folder (None: shipped files only, nothing can be saved)."""

    def __init__(self, folder: Path | str | None, shipped: Traversable | None = None):
        self.folder = None if folder is None else Path(folder)
        self._shipped = shipped_data() if shipped is None else shipped
        self.reload()

    # ── Loading ─────────────────────────────────────────────────────────

    def reload(self):
        """(Re)read every file."""
        self._problems: list[Problem] = []
        self._unreadable: set[Path] = set()            # files of yours that couldn't be used
        profiles = {}
        for key, candidates in self._candidates('profiles', read_profile).items():
            chosen = self._choose(candidates, lambda profile: profile)
            if chosen is not None:
                profiles[key] = chosen[1]
        self.profiles: Mapping[str, Profile] = MappingProxyType(profiles)
        renderers, sources = {}, {}
        for key, candidates in self._candidates('bindings', read_binding).items():
            chosen = self._choose(candidates, self._compile)
            if chosen is not None:
                sources[key], renderers[key] = chosen
        self.renderers: Mapping[str, Renderer] = MappingProxyType(renderers)
        self._sources = sources
        self.vocabulary = self._load_own(VOCABULARY_FILE, lambda path: Vocabulary.from_json(read_file(path)),
                                         Vocabulary())
        self.patch = self._load_own(PATCH_FILE, read_patch, Patch())

    def _candidates(self, kind: str, read) -> dict[str, list[_Candidate]]:
        """Every file of `kind` by key, yours before shipped, each read (or its error)."""
        found: dict[str, list[_Candidate]] = {}
        sources = [(YOURS, self.folder / kind)] if self.folder is not None else []
        for source, folder in [*sources, (SHIPPED, self._shipped.joinpath(kind))]:
            for key, item in _json_files(folder):
                label = f'{kind}/{key}.json' + (' (shipped)' if source == SHIPPED else '')
                with as_file(item) as path:
                    try:
                        value, error = read(path, key), None
                    except FixtureError as e:
                        value, error = None, e
                    found.setdefault(key, []).append(
                        _Candidate(source, label, Path(path) if source == YOURS else None, value, error))
        return dict(sorted(found.items()))

    def _choose(self, candidates: list['_Candidate'], use) -> tuple[str, object] | None:
        """(source, use(value)) for the first candidate that reads and that
        `use` accepts; the ones that failed before it become problems."""
        failed: list[tuple[_Candidate, FixtureError]] = []
        chosen = None
        for candidate in candidates:
            try:
                if candidate.error is not None:
                    raise candidate.error
                chosen = candidate.source, use(candidate.value)
                break
            except FixtureError as e:
                failed.append((candidate, e))
        for candidate, error in failed:
            message = str(error.in_file(''))                      # the place inside the file, and what's wrong
            if chosen is not None:                                 # yours come first, so it's the shipped one
                message += ' (using the shipped one instead)'
            self._problems.append(Problem(candidate.label, message))
            if candidate.path is not None:
                self._unreadable.add(candidate.path)
        return chosen

    def _compile(self, binding: Binding) -> Renderer:
        profile = self.profiles.get(binding.profile)
        if profile is None:
            raise BindingError(f'its profile "{binding.profile}" isn\'t available', 'profile')
        return Renderer(binding.resolve(profile))

    def _load_own(self, name: str, read, default):
        """One of your files (patch.json, vocabulary.json); `default` if it's missing or unreadable."""
        if self.folder is None or not (self.folder / name).is_file():
            return default
        path = self.folder / name
        try:
            return read(path)
        except FixtureError as e:
            self._problems.append(Problem(name, f'{e.in_file("")} (starting without it)'))
            self._unreadable.add(path)
            return default

    # ── What's available ────────────────────────────────────────────────

    @property
    def problems(self) -> tuple[Problem, ...]:
        return tuple(self._problems)

    def source(self, key: str) -> str:
        """'yours' or 'shipped': where the fixture type in use came from."""
        return self._sources[key]

    def types(self) -> list[tuple[str, str]]:
        """(key, name) of every usable fixture type, by name."""
        return sorted(((key, r.name) for key, r in self.renderers.items()), key=lambda item: item[1].casefold())

    def rig(self) -> Rig:
        """The patch with the renderers for its types."""
        return Rig(self.patch, self.renderers)

    # ── Saving (always to your folder) ──────────────────────────────────

    def _target(self, *parts: str) -> Path:
        if self.folder is None:
            raise RuntimeError('no fixtures folder to save to')
        path = self.folder.joinpath(*parts)
        if path in self._unreadable and path.exists():
            _set_aside(path)
            self._unreadable.discard(path)
        return path

    def save_patch(self, patch: Patch):
        write_patch(self._target(PATCH_FILE), patch)
        self.patch = patch

    def save_vocabulary(self, vocabulary: Vocabulary):
        write_file(self._target(VOCABULARY_FILE), vocabulary.to_json())
        self.vocabulary = vocabulary

    def save_binding(self, binding: Binding) -> Renderer:
        """Save `binding` (with its key) to your folder, where it overrides
        a shipped one, and use it from now on. Checked first: a binding
        that doesn't fit its profile raises and nothing is written."""
        if not binding.key:
            raise ValueError('the binding needs its key to be saved')
        profile = self.profiles.get(binding.profile)
        if profile is None:
            raise ValueError(f'its profile "{binding.profile}" isn\'t available')
        renderer = Renderer(binding.resolve(profile))
        write_binding(self._target('bindings', *f'{binding.key}.json'.split('/')), binding)
        self.renderers = MappingProxyType({**self.renderers, binding.key: renderer})
        self._sources[binding.key] = YOURS
        return renderer
