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

from PyQt5.QtCore import QCoreApplication, QEvent, QSettings  # noqa: E402
from PyQt5.QtWidgets import QApplication            # noqa: E402

from fakes import udp as fake_udp                  # noqa: E402
from helpers import WindowHarness                  # noqa: E402


@pytest.fixture(scope='session')
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def styled_app(qapp):
    """The app with PyLZR's real look (fonts, palette, stylesheet), put back
    afterwards so other tests keep running unstyled."""
    import pyqtgraph as pg

    from pylzr.gui import style
    saved = (qapp.style().objectName(), qapp.palette(), qapp.font(), qapp.styleSheet(),
             pg.getConfigOption('background'), pg.getConfigOption('foreground'))
    style.apply(qapp)
    yield qapp
    name, palette, font, sheet, background, foreground = saved
    qapp.setStyleSheet(sheet)
    qapp.setStyle(name)
    qapp.setPalette(palette)
    qapp.setFont(font)
    pg.setConfigOptions(background=background, foreground=foreground)


@pytest.fixture(autouse=True)
def _fresh_state(tmp_path):
    """Every test starts on a simulated macOS with default devices and no
    saved settings (QSettings points at a fresh temp folder, never at the
    real user config)."""
    fake_rtmidi.reset('mac')
    fake_pyaudio.reset()
    fake_udp.reset()
    QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(tmp_path / 'config'))
    yield
    # Widgets a test let go of with deleteLater() are deleted now: no event
    # loop runs between tests, and left alive they pile up and slow every
    # later stylesheet change
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    """Windows send DMX and look for nodes through fake sockets, so no test
    ever puts Art-Net packets on the real network or depends on this
    computer's network adapters (tests of pylzr.dmx pass FakeSocket or a
    loopback address themselves)."""
    from functools import partial

    import pylzr.gui.main_window as main_window
    from pylzr.dmx import DMXOutput, NodeDiscovery
    monkeypatch.setattr(main_window, 'DMXOutput', partial(DMXOutput, socket_factory=fake_udp.FakeSocket))
    monkeypatch.setattr(main_window, 'NodeDiscovery', partial(NodeDiscovery, socket_factory=fake_udp.FakeSocket,
                                                              broadcasts=lambda: ['10.255.255.255']))


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
