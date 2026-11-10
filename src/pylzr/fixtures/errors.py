"""Errors for fixture files and values. Each one says where the problem is:
the file, and the path inside it, e.g.

    bindings/gruolin/rgb-beam-36ch.json: attributes[3].range: 0–300 is outside 0–255

They're ValueErrors (bad data), so code that only cares that a value was
rejected can catch ValueError.
"""


def join_where(outer: str, inner: str) -> str:
    """A path inside a JSON file: 'attributes[3]' + 'range' gives
    'attributes[3].range'; an index part ('[2]') attaches directly; empty
    parts are skipped."""
    if not outer:
        return inner
    if not inner:
        return outer
    return outer + inner if inner.startswith('[') else f'{outer}.{inner}'


class FixtureError(ValueError):
    """A problem in fixture data. `where` is the path inside the data,
    `file` the file it came from ('' if not known yet)."""

    def __init__(self, message: str, where: str = '', file: str = ''):
        super().__init__(message, where, file)
        self.message, self.where, self.file = message, where, file

    def __str__(self) -> str:
        location = ': '.join(part for part in (self.file, self.where) if part)
        return f'{location}: {self.message}' if location else self.message

    def within(self, outer: str) -> 'FixtureError':
        """The same error, inside `outer` (e.g. 'modes[0]')."""
        return type(self)(self.message, join_where(outer, self.where), self.file)

    def in_file(self, file: str) -> 'FixtureError':
        """The same error, naming the file it came from."""
        return type(self)(self.message, self.where, str(file))


class ProfileError(FixtureError):
    """A problem in an OFL fixture profile."""


class BindingError(FixtureError):
    """A problem in a binding (how attributes drive a fixture's channels)."""


class PatchError(FixtureError):
    """A problem in the patch (which fixtures are at which addresses)."""


class VocabularyError(FixtureError):
    """A problem in the pattern categories and scales."""
