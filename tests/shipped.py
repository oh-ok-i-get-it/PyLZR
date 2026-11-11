"""The shipped fixture files, loaded as package resources (as an installed
PyLZR would), for tests."""

from functools import cache
from importlib.resources import as_file, files

from pylzr.fixtures import compile_fixture, read_binding, read_profile

GRUOLIN = 'gruolin/rgb-beam-36ch'


def resource(*parts):
    return files('pylzr.fixtures').joinpath('data', *parts)


@cache
def binding(key: str = GRUOLIN):
    with as_file(resource('bindings', f'{key}.json')) as path:
        return read_binding(path, key)


@cache
def renderer(key: str = GRUOLIN):
    b = binding(key)
    with as_file(resource('profiles', f'{b.profile}.json')) as path:
        return compile_fixture(b, read_profile(path, b.profile))


def channels(**named: int) -> dict[int, int]:
    """{1-based channel: value} from ch5=…, ch22=… keywords, for readable expectations."""
    return {int(key.removeprefix('ch')): value for key, value in named.items()}
