"""Keeps the package's layers apart.

pylzr.fixtures (what fixtures are and how they're driven) must stay pure: no
Qt, sockets, audio, MIDI or numpy, and no imports from the app's other
layers. Then it can be used anywhere (the GUI, scenes, the ML model,
command-line tools) and is tested with plain data.
"""

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

SRC      = Path(__file__).resolve().parents[1] / 'src'
FIXTURES = SRC / 'pylzr' / 'fixtures'

HEAVY = ('PyQt5', 'socket', 'pyaudio', 'rtmidi', 'numpy')
OTHER_LAYERS = ('gui', 'dmx', 'audio', 'midi', 'analysis', 'engine')


def test_fixtures_package_loads_nothing_heavy():
    """Checked in a fresh interpreter (this test process has Qt loaded
    already), counting only what pylzr.fixtures adds to `import pylzr`.
    (`import pylzr` reads its version via importlib.metadata, which loads
    socket through the email package; direct socket imports are caught by
    the static check below.)"""
    modules = sorted(p.stem for p in FIXTURES.glob('*.py') if p.stem != '__init__')
    code = (
        'import importlib, json, sys\n'
        'import pylzr\n'
        'before = set(sys.modules)\n'
        'import pylzr.fixtures\n'
        f'for name in {modules!r}: importlib.import_module("pylzr.fixtures." + name)\n'
        'added = set(sys.modules) - before\n'
        f'print(json.dumps(sorted(m for m in added if m.split(".")[0] in {HEAVY!r})))\n'
    )
    env = {**os.environ, 'PYTHONPATH': str(SRC)}
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True, env=env)
    assert json.loads(out.stdout) == []


def imported_modules(path: Path) -> list[str]:
    """Every module `path` imports, relative imports resolved within pylzr."""
    package = ['pylzr', 'fixtures']
    names = []
    for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
        if isinstance(node, ast.Import):
            names += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            base = package[:len(package) - node.level + 1] if node.level else []
            if node.module:
                names.append('.'.join(base + [node.module]))
            else:                       # 'from .. import gui' imports the module gui
                names += ['.'.join(base + [alias.name]) for alias in node.names]
    return names


def test_fixtures_modules_import_no_other_layer():
    """Static check, so an import inside a function can't slip through either."""
    forbidden = HEAVY + tuple(f'pylzr.{layer}' for layer in OTHER_LAYERS)
    found = {
        path.name: [name for name in imported_modules(path)
                    if any(name == f or name.startswith(f + '.') for f in forbidden)]
        for path in FIXTURES.glob('*.py')
    }
    assert {name: bad for name, bad in found.items() if bad} == {}


def test_import_resolution_helper(tmp_path):
    """imported_modules() itself: every import form resolves to the right module."""
    sample = tmp_path / 'sample.py'
    sample.write_text('import re, os.path\n'
                      'from .attributes import Kind\n'
                      'from . import errors\n'
                      'from ..gui import theme\n'
                      'from .. import dmx\n'
                      'def later():\n'
                      '    from PyQt5.QtCore import QTimer\n', encoding='utf-8')
    assert imported_modules(sample) == ['re', 'os.path', 'pylzr.fixtures.attributes', 'pylzr.fixtures.errors',
                                        'pylzr.gui', 'pylzr.dmx', 'PyQt5.QtCore']
