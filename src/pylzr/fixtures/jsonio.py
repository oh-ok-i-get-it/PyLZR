"""Reading and writing PyLZR's JSON data files (bindings, patch, vocabulary).

- read_file():   UTF-8 JSON (a BOM from Windows editors is fine); a syntax
                 error names its line and column.
- ObjectReader:  reads one JSON object strictly. Wrong types and unknown keys
                 (e.g. a typo like "centr") are errors naming their exact
                 place, such as 'attributes[2].centr'.
- upgrade():     checks a file's "version" and brings older files up to date.
- write_file():  stable formatting and an atomic save, so a crash never
                 leaves half a file and saved files diff cleanly.
"""

import contextlib
import difflib
import json
import os
import tempfile
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

from .errors import FixtureError, join_where

_LINE_WIDTH = 100     # lists of plain values up to this wide stay on one line


def describe(value: Any) -> str:
    """How a JSON value is named in error messages."""
    if value is None:
        return 'null'
    if isinstance(value, bool):
        return 'true/false'
    if isinstance(value, (int, float)):
        return f'the number {value}'
    if isinstance(value, str):
        return f'the text "{value}"'
    return 'a list' if isinstance(value, list) else 'an object'


_KIND_NAMES = {str: 'text', int: 'a whole number', float: 'a number', bool: 'true or false',
               list: 'a list', dict: 'an object'}


def check_type(value: Any, kind: type | tuple[type, ...], where: str = '',
               error: type[FixtureError] = FixtureError) -> Any:
    """`value` if it is one of the JSON kinds in `kind`, else raise. JSON's
    true/false never counts as a number; a whole number is fine where a
    number is wanted (and is returned as a float)."""
    kinds = kind if isinstance(kind, tuple) else (kind,)
    if isinstance(value, bool):
        ok = bool in kinds
    elif isinstance(value, int) and float in kinds and int not in kinds:
        return float(value)
    else:
        ok = isinstance(value, kinds)
    if not ok:
        wanted = ' or '.join(_KIND_NAMES.get(k, k.__name__) for k in kinds)
        raise error(f'must be {wanted}, not {describe(value)}', where)
    return value


class ObjectReader:
    """Reads one JSON object, strictly. Ask for each key with required() or
    optional(), then call finish(): any key nobody asked for is an error
    (with a "did you mean" hint), so typos never pass silently.

    Errors are raised as `error` (e.g. BindingError) and name their place:
    the reader's own `where` joined with the key, e.g. 'attributes[2].range'.
    """

    def __init__(self, data: Any, where: str = '', error: type[FixtureError] = FixtureError):
        if not isinstance(data, dict):
            raise error(f'must be an object, not {describe(data)}', where)
        self._data = data
        self.where = where
        self.error = error
        self._asked: set[str] = set()

    def path(self, key: str) -> str:
        """Where `key` of this object is, e.g. 'attributes[2].range'."""
        return join_where(self.where, key)

    def fail(self, message: str, key: str = '') -> FixtureError:
        """An error at this object (or at its `key`), to raise."""
        return self.error(message, self.path(key) if key else self.where)

    def keys(self) -> list[str]:
        """The object's keys, in file order."""
        return list(self._data)

    def has(self, key: str) -> bool:
        self._asked.add(key)
        return key in self._data

    def rest(self) -> dict[str, Any]:
        """Every key not asked for yet, with its value; they then count as
        read (for objects whose other keys are checked by the caller)."""
        rest = {key: value for key, value in self._data.items() if key not in self._asked}
        self._asked.update(rest)
        return rest

    def required(self, key: str, kind: type | tuple[type, ...]) -> Any:
        if not self.has(key):
            raise self.fail(f'"{key}" is missing')
        return check_type(self._data[key], kind, self.path(key), self.error)

    def optional(self, key: str, kind: type | tuple[type, ...], default: Any = None) -> Any:
        if not self.has(key):
            return default
        return check_type(self._data[key], kind, self.path(key), self.error)

    def child(self, key: str, required: bool = True) -> 'ObjectReader | None':
        """A reader for the object stored at `key` (None if optional and absent)."""
        data = self.required(key, dict) if required else self.optional(key, dict)
        return None if data is None else ObjectReader(data, self.path(key), self.error)

    def each(self, key: str, required: bool = True) -> Iterator['ObjectReader']:
        """A reader for every object in the list at `key`, in order."""
        items = self.required(key, list) if required else self.optional(key, list, [])
        for i, item in enumerate(items):
            yield ObjectReader(item, join_where(self.path(key), f'[{i}]'), self.error)

    def finish(self):
        """Raise if the object has a key nobody asked for."""
        unknown = [key for key in self._data if key not in self._asked]
        if unknown:
            key = unknown[0]
            close = difflib.get_close_matches(key, sorted(self._asked), n=1)
            hint = f' (did you mean "{close[0]}"?)' if close else ''
            raise self.fail(f'unknown key "{key}"{hint}')


def read_file(path: Path | str, error: type[FixtureError] = FixtureError) -> Any:
    """The JSON value in the file at `path`. Problems raise `error`, naming the file."""
    try:
        text = Path(path).read_text(encoding='utf-8-sig')
    except UnicodeDecodeError as e:
        raise error('is not UTF-8 text', file=str(path)) from e
    except OSError as e:
        raise error(f'cannot be read ({e.strerror or e})', file=str(path)) from e
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise error(f'is not valid JSON: {e.msg} (line {e.lineno}, column {e.colno})', file=str(path)) from e


def upgrade(data: Any, current: int, migrations: Mapping[int, Callable[[dict], dict]] | None = None,
            where: str = '', error: type[FixtureError] = FixtureError) -> dict:
    """Check data's "version" and bring it up to `current`, one version at a
    time: migrations[n] turns a version-n object into version n+1. A file
    from a newer PyLZR is refused rather than misread."""
    if not isinstance(data, dict):
        raise error(f'must be an object, not {describe(data)}', where)
    if 'version' not in data:
        raise error('"version" is missing', where)
    version = data['version']
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise error(f'must be a whole number from 1, not {describe(version)}', join_where(where, 'version'))
    if version > current:
        raise error(f'was made by a newer PyLZR (file version {version}; this version reads up to '
                    f'{current}). Update PyLZR to use it.', where)
    migrations = migrations or {}
    while version < current:
        if version not in migrations:
            raise error(f'version {version} can no longer be read', where)
        data = migrations[version](dict(data))
        version += 1
        data['version'] = version
    return data


def dumps(data: Any) -> str:
    """Stable text for a data file: 2-space indent, keys in the order given,
    non-ASCII kept as is (e.g. '→'), short lists of plain values on one line
    (e.g. "range": [0, 255]), and a final newline."""
    return _format(data, 0) + '\n'


def _format(value: Any, depth: int) -> str:
    pad, inner = '  ' * depth, '  ' * (depth + 1)
    if isinstance(value, dict):
        if not value:
            return '{}'
        items = [f'{inner}{json.dumps(str(k), ensure_ascii=False)}: {_format(v, depth + 1)}'
                 for k, v in value.items()]
        return '{\n' + ',\n'.join(items) + f'\n{pad}}}'
    if isinstance(value, list):
        if not value:
            return '[]'
        if not any(isinstance(item, (dict, list)) for item in value):
            one_line = '[' + ', '.join(json.dumps(item, ensure_ascii=False) for item in value) + ']'
            if len(inner) + len(one_line) <= _LINE_WIDTH:
                return one_line
        items = [inner + _format(item, depth + 1) for item in value]
        return '[\n' + ',\n'.join(items) + f'\n{pad}]'
    return json.dumps(value, ensure_ascii=False)


def write_file(path: Path | str, data: Any):
    """Save `data` as JSON at `path`, atomically: it's written to a
    temporary file in the same folder and then swapped in, so `path` always
    holds either the old or the new file, never half of one. Missing folders
    are created. Line endings are '\\n' on every OS."""
    path = Path(path)
    text = dumps(data)                  # fails before anything is touched
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='\n') as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise
