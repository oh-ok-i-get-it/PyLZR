import json
import os
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / 'src'


def test_importing_package_is_lightweight():
    """`import pylzr` must not pull in Qt, audio or MIDI. Checked in a fresh
    interpreter, since this test process has already imported them."""
    code = (
        'import json, sys, pylzr; '
        'print(json.dumps({"heavy": [m for m in ("PyQt5", "pyaudio", "rtmidi", "numpy") if m in sys.modules], '
        '"version": pylzr.__version__}))'
    )
    env = {**os.environ, 'PYTHONPATH': str(SRC)}
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True, env=env)
    result = json.loads(out.stdout)
    assert result['heavy'] == []
    assert result['version']
