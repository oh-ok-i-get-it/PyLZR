"""Shared pytest setup.

- Qt runs offscreen, so no display is needed (CI, SSH, etc.).
- rtmidi and pyaudio are replaced by in-memory fakes from tests/fakes/, so the
  suite runs the same on Windows, macOS and Linux without audio or MIDI
  hardware. This must happen before anything imports pylzr.
"""

import importlib.util
import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

_FAKES = Path(__file__).parent / 'fakes'


def _install_fake(name: str):
    spec = importlib.util.spec_from_file_location(name, _FAKES / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    sys.modules[name] = module
    return module


fake_rtmidi  = _install_fake('rtmidi')
fake_pyaudio = _install_fake('pyaudio')

from PyQt5.QtCore import QCoreApplication, QEvent  # noqa: E402
from PyQt5.QtWidgets import QApplication            # noqa: E402

from helpers import WindowHarness                  # noqa: E402


@pytest.fixture(scope='session')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture(autouse=True)
def _fresh_state():
    """Every test starts on a simulated macOS with default devices."""
    fake_rtmidi.reset('mac')
    fake_pyaudio.reset()


@pytest.fixture(params=['win', 'mac'])
def os_name(request):
    """Run the test once per simulated OS (MIDI backend)."""
    fake_rtmidi.reset(request.param)
    return request.param


@pytest.fixture
def make_window(qapp):
    """Factory for harnessed main windows; closes and deletes them afterwards."""
    from pylzr.gui import MainWindow

    created = []

    def factory() -> WindowHarness:
        harness = WindowHarness(MainWindow())
        created.append(harness)
        return harness

    yield factory

    for harness in created:
        harness.close()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.fixture
def harness(make_window) -> WindowHarness:
    return make_window()
