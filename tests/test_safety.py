"""The emergency stop: EmergencyStop, the exception hook, and what they do in
the real main window (DMX goes to the fake network, MIDI to the fake rtmidi;
nothing here reaches hardware)."""

import ast
import atexit
import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np
import pyaudio as fake_pyaudio   # the fake, installed by conftest
import pytest
import rtmidi as fake_rtmidi
from PyQt5.QtCore import QObject, Qt, pyqtSignal
from PyQt5.QtWidgets import QApplication

import pylzr.__main__
import pylzr.gui
import pylzr.gui.style
from fakes import udp as fake_udp
from fakes.udp import FakeSocket
from helpers import dmx_packets, note_messages, note_ons, tone_chunks, wait_for_note_offs, wait_until
from pylzr.core.safety import EmergencyStop, install_excepthook
from pylzr.dmx.dmx_output import BLACKOUT_REPEATS

SPACE_ON  = [0x90, 106, 112]
SPACE_OFF = [0x80, 106, 0]
ALL_OFF   = [0xB0, 123, 0]
DARK      = [bytes(512)] * 3

ROOT = Path(__file__).resolve().parent.parent


def frames() -> list[bytes]:
    return [p['data'] for p in dmx_packets()]


def set_mode(window, mode):
    window.settings_panel.set_control_mode(mode)


@pytest.fixture
def hooks(monkeypatch):
    """sys/threading excepthooks are put back after the test (pytest 9 installs its own threading hook per session)."""
    monkeypatch.setattr(sys, 'excepthook', sys.excepthook)
    monkeypatch.setattr(threading, 'excepthook', threading.excepthook)


@pytest.fixture
def safety(hooks) -> EmergencyStop:
    stop = EmergencyStop()
    install_excepthook(stop)
    return stop


class _Raiser(QObject):
    fire = pyqtSignal()


def raise_in_a_slot(exc: BaseException | None = None):
    """Raise `exc` inside a Qt slot on the GUI thread. Without our hook PyQt
    calls qFatal, which would abort the whole pytest run."""
    assert sys.excepthook is not sys.__excepthook__
    raiser = _Raiser()

    def slot():
        raise exc if exc is not None else RuntimeError('boom')

    raiser.fire.connect(slot)
    raiser.fire.emit()


def unhandled(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.exc_info]


def handle(exc: BaseException):
    """Hand `exc`, raised right here, to sys.excepthook."""
    try:
        raise exc
    except BaseException:
        sys.excepthook(*sys.exc_info())


# ── EmergencyStop ────────────────────────────────────────────────────────

def test_trigger_with_nothing_registered_is_harmless(caplog):
    stop = EmergencyStop()
    assert not stop.triggered
    with caplog.at_level(logging.DEBUG, logger='pylzr'):
        stop.trigger('x')
    assert stop.triggered
    assert 'nothing registered' in caplog.text


def test_trigger_runs_every_stop_in_registration_order():
    stop, ran = EmergencyStop(), []
    for name in 'abc':
        stop.register(name, lambda name=name: ran.append(name))
    stop.trigger('x')
    assert ran == ['a', 'b', 'c']


def test_registering_a_name_again_replaces_it_in_place():
    stop, ran = EmergencyStop(), []
    stop.register('a', lambda: ran.append('a1'))
    stop.register('b', lambda: ran.append('b'))
    stop.register('a', lambda: ran.append('a2'))
    stop.trigger('x')
    assert ran == ['a2', 'b']


def test_unregister_removes_a_stop_and_ignores_unknown_names():
    stop, ran = EmergencyStop(), []
    stop.register('a', lambda: ran.append('a'))
    stop.register('b', lambda: ran.append('b'))
    stop.unregister('a')
    stop.unregister('never registered')
    stop.trigger('x')
    assert ran == ['b']


def test_a_stop_that_raises_is_logged_and_the_rest_still_run(caplog):
    stop, ran = EmergencyStop(), []

    def broken():
        raise RuntimeError('stuck')

    stop.register('first', lambda: ran.append('first'))
    stop.register('broken', broken)
    stop.register('last', lambda: ran.append('last'))
    stop.trigger('x')
    assert ran == ['first', 'last']
    errors = [r for r in caplog.records if r.levelname == 'ERROR']
    assert len(errors) == 1 and '"broken"' in errors[0].getMessage()
    assert stop.triggered


def test_trigger_twice_runs_every_stop_twice():
    stop, ran = EmergencyStop(), []
    stop.register('a', lambda: ran.append('a'))
    stop.trigger('x')
    stop.trigger('y')
    assert ran == ['a', 'a']


def test_trigger_from_inside_a_stop_is_ignored():
    stop, ran = EmergencyStop(), []
    stop.register('a', lambda: (ran.append('a'), stop.trigger('again')))
    stop.register('b', lambda: ran.append('b'))
    stop.trigger('x')
    assert ran == ['a', 'b']


def test_trigger_from_another_thread_runs_the_stops_there():
    stop, where = EmergencyStop(), []
    stop.register('a', lambda: where.append(threading.current_thread().name))
    worker = threading.Thread(target=stop.trigger, args=('x',), name='the-worker')
    worker.start()
    worker.join()
    assert where == ['the-worker']


def test_stops_run_before_the_summary_is_logged(caplog):
    stop = EmergencyStop()
    stop.register('a', lambda: logging.getLogger('pylzr.test').warning('stop ran'))
    stop.trigger('x')
    messages = [r.getMessage() for r in caplog.records]
    assert messages[0] == 'stop ran'
    assert messages[1].startswith('Emergency stop (x):')


# ── The hook ─────────────────────────────────────────────────────────────

def test_install_replaces_both_hooks(hooks):
    before = sys.excepthook, threading.excepthook
    install_excepthook(EmergencyStop())
    assert sys.excepthook is not before[0]
    assert threading.excepthook is not before[1]


def test_unhandled_exception_stops_first_then_logs_the_traceback_once(safety, caplog):
    seen = []
    safety.register('probe', lambda: seen.append([r for r in caplog.records if r.levelno >= logging.ERROR]))
    handle(RuntimeError('boom'))
    assert seen == [[]]                                  # the stop ran before any ERROR was logged
    records = unhandled(caplog)
    assert len(records) == 1
    assert records[0].exc_info[0] is RuntimeError and records[0].name == 'pylzr.safety'


def test_a_repeating_error_logs_at_1_2_4_8_and_stops_every_time(safety, caplog):
    ran = []
    safety.register('a', lambda: ran.append(1))
    for _ in range(10):
        try:
            raise RuntimeError('again')
        except RuntimeError:
            sys.excepthook(*sys.exc_info())
    assert len(ran) == 10
    assert len(unhandled(caplog)) == 1
    again = [r.getMessage() for r in caplog.records if 'same error again' in r.getMessage()]
    assert [m.split('(')[1].split(' ')[0] for m in again] == ['2', '4', '8']


def test_different_errors_each_get_their_traceback(safety, caplog):
    try:
        raise RuntimeError('one')
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    try:
        raise RuntimeError('two')
    except RuntimeError:
        sys.excepthook(*sys.exc_info())
    assert len(unhandled(caplog)) == 2


def test_on_handled_runs_once_after_the_first_error(hooks):
    calls = []
    install_excepthook(EmergencyStop(), on_handled=lambda: calls.append(1))
    for _ in range(3):
        handle(RuntimeError('boom'))
    assert calls == [1]


def test_exception_in_a_python_thread_is_handled(safety, caplog):
    ran = []
    safety.register('a', lambda: ran.append(1))

    def boom():
        raise RuntimeError('thread boom')

    worker = threading.Thread(target=boom, name='boomer')
    worker.start()
    worker.join()
    assert ran == [1]
    records = unhandled(caplog)
    assert len(records) == 1 and 'boomer' in records[0].getMessage()


def test_systemexit_in_a_thread_is_ignored(safety, caplog):
    ran = []
    safety.register('a', lambda: ran.append(1))
    worker = threading.Thread(target=sys.exit)
    worker.start()
    worker.join()
    assert ran == []
    assert not [r for r in caplog.records if r.name == 'pylzr.safety']


def test_ctrl_c_stops_then_asks_to_quit(hooks, caplog):
    reasons, handled, interrupted = [], [], []
    stop = EmergencyStop()
    stop.register('a', lambda: reasons.append('ran'))
    install_excepthook(stop, on_handled=lambda: handled.append(1), on_interrupt=lambda: interrupted.append(1))
    handle(KeyboardInterrupt())
    assert reasons == ['ran']
    assert 'interrupted' in [r.getMessage() for r in caplog.records if 'Emergency stop' in r.getMessage()][0]
    warnings = [r for r in caplog.records if 'Interrupted (Ctrl+C)' in r.getMessage()]
    assert len(warnings) == 1 and warnings[0].levelname == 'WARNING' and not warnings[0].exc_info
    assert not unhandled(caplog)
    assert interrupted == [1] and handled == []


def test_the_hook_never_raises(hooks, capsys):
    def broken():
        raise ValueError('hook failure')

    install_excepthook(EmergencyStop(), on_handled=broken)
    handle(RuntimeError('boom'))                         # returns
    err = capsys.readouterr().err
    assert 'RuntimeError: boom' in err and 'ValueError: hook failure' in err


def test_safety_module_imports_no_qt():
    tree = ast.parse((ROOT / 'src' / 'pylzr' / 'core' / 'safety.py').read_text(encoding='utf-8'))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or '')
    assert not [name for name in imported if name.startswith('PyQt5')]


# ── In the app ───────────────────────────────────────────────────────────

def test_exception_in_a_gui_slot_blacks_out_and_the_app_keeps_running(safety, make_window, qapp, caplog):
    h = make_window(safety=safety)
    w = h.window
    set_mode(w, 'DMX')
    w.dmx_out.universe.set(1, 255)
    n = len(dmx_packets())
    raise_in_a_slot()
    assert frames()[n:] == DARK                          # before any event processing
    qapp.processEvents()
    assert not w.dmx_out.active
    assert frames()[-3:] == DARK
    assert w.settings_panel._dmx_val.text() == 'Off'
    assert w.output.active == 'DMX' and w.settings_panel._mode_combo.currentData() == 'DMX'   # Q1
    assert len(unhandled(caplog)) == 1
    assert w.log_panel._text.toPlainText().count('RuntimeError: boom') == 1
    h.key(Qt.Key_Q)
    assert 'Key:' in w.controls.status_label.text()


def test_switching_control_mode_after_the_stop_resumes_dmx(safety, make_window, qapp):
    w = make_window(safety=safety).window
    set_mode(w, 'DMX')
    w.dmx_out.universe.set(1, 255)
    raise_in_a_slot()
    qapp.processEvents()
    assert not w.dmx_out.active
    set_mode(w, 'MIDI')
    set_mode(w, 'DMX')
    assert w.dmx_out.active
    assert frames()[-1][0] == 255


def _raise_once_in_fft(monkeypatch):
    """The first FFT on the worker thread raises. (Replacing FFTWorker.process itself doesn't work: PyQt has
    already registered the original as the slot, and the replacement is never called.)"""
    real_rfft = np.fft.rfft
    calls = []

    def rfft(*args, **kwargs):
        if threading.current_thread() is not threading.main_thread():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError('fft boom')
        return real_rfft(*args, **kwargs)

    monkeypatch.setattr(np.fft, 'rfft', rfft)


def _deliver_one_chunk(w):
    fake_pyaudio.deliver(tone_chunks(1, (440, 8000))[0].tobytes(), stream=w.engine.audio._stream)


def test_exception_in_the_fft_thread_blacks_out_and_analysis_continues(safety, make_window, monkeypatch, caplog):
    _raise_once_in_fft(monkeypatch)
    h = make_window(safety=safety)
    w = h.window
    set_mode(w, 'DMX')
    _deliver_one_chunk(w)
    wait_until(lambda: not w.dmx_out.active)
    assert frames()[-3:] == DARK
    records = unhandled(caplog)
    assert len(records) == 1 and records[0].threadName != 'MainThread'
    h.feed(tone_chunks(2, (440, 8000)))                  # the FFT thread is alive


def test_no_show_frame_follows_the_blackout_when_the_fft_thread_raises(safety, make_window, monkeypatch):
    _raise_once_in_fft(monkeypatch)
    h = make_window(safety=safety)
    w = h.window
    w.dmx_out.universe.set(1, 255)                       # every frame before the stop is lit
    set_mode(w, 'DMX')
    real_sendto = FakeSocket.sendto
    panic_sends = {'started': 0, 'finished': 0}

    def slow_off_main(self, data, address):
        off_main = threading.current_thread() is not threading.main_thread()
        if off_main:
            panic_sends['started'] += 1
            time.sleep(0.02)                             # panic()'s three sends span more than two 25 ms ticks
        try:
            return real_sendto(self, data, address)
        finally:
            if off_main:
                panic_sends['finished'] += 1

    real_send = w.dmx_out._send
    ticks_during_panic = 0

    def counting_send(data):                             # the GUI thread's sends (its timer ticks)
        nonlocal ticks_during_panic
        if panic_sends['started'] and panic_sends['finished'] < BLACKOUT_REPEATS and data != bytes(512):
            ticks_during_panic += 1
        real_send(data)

    monkeypatch.setattr(FakeSocket, 'sendto', slow_off_main)
    monkeypatch.setattr(w.dmx_out, '_send', counting_send)
    _deliver_one_chunk(w)
    wait_until(lambda: not w.dmx_out.active)
    assert ticks_during_panic > 0                        # the race was exercised: a tick ran while panic() was sending
    sent = frames()
    first_dark = next(i for i, f in enumerate(sent) if f == bytes(512))
    assert first_dark > 0
    assert all(f == bytes(512) for f in sent[first_dark:])


def test_midi_mode_stop_sends_all_notes_off_then_space_and_keeps_running(safety, make_window):
    h = make_window(safety=safety)
    raise_in_a_slot()
    assert note_messages() == [ALL_OFF, SPACE_ON, SPACE_OFF]
    assert dmx_packets() == []
    h.key(Qt.Key_Q)
    wait_for_note_offs()
    assert [73, 112] in note_ons()


def test_later_stops_send_all_notes_off_only(make_window):
    w = make_window().window
    for _ in range(3):
        w.safety.trigger('t')
    assert note_messages() == [ALL_OFF, SPACE_ON, SPACE_OFF, ALL_OFF, ALL_OFF]        # Q10


def test_switching_control_mode_to_midi_rearms_space(make_window):
    w = make_window().window
    w.safety.trigger('t')
    set_mode(w, 'DMX')
    set_mode(w, 'MIDI')
    w.safety.trigger('t')
    assert note_ons() == [[106, 112], [106, 112]]


def test_space_stays_armed_until_it_reaches_the_port(make_window):
    fake_rtmidi.reset('win')                             # no PyLZR port: MIDI is not connected
    w = make_window().window
    w.safety.trigger('t')
    assert fake_rtmidi.sent == [] and fake_udp.sent == []
    fake_rtmidi.ports.append('PyLZR-MIDI 1')
    w.midi_out.open('PyLZR-MIDI 1')
    w.safety.trigger('t')
    assert note_messages() == [ALL_OFF, SPACE_ON, SPACE_OFF]


def test_two_stops_at_once_send_space_once(make_window):
    """Deterministic: a second stop starts on another thread while the first
    is between reading the SPACE arm and clearing it. With the arm's lock the
    second waits for the first's test-and-clear; without it both see it armed."""
    w = make_window().window
    second = threading.Thread(target=w.safety.trigger, args=('second',))

    class ArmReadPauses(type(w)):
        @property
        def _space_armed(self):
            armed = self.__dict__['_space_armed']
            if threading.current_thread() is threading.main_thread() and second.ident is None:
                second.start()
                second.join(0.1)                         # with the lock, the second stop is still waiting for it
            return armed

        @_space_armed.setter
        def _space_armed(self, value):
            self.__dict__['_space_armed'] = value

    w.__class__ = ArmReadPauses
    w.safety.trigger('first')
    second.join()
    msgs = note_messages()
    assert msgs.count(SPACE_ON) == 1 and msgs.count(ALL_OFF) == 2


def test_a_stop_during_the_switch_to_midi_sends_space(make_window, monkeypatch):
    """A stop landing just after output.select('MIDI') (e.g. from the FFT
    thread) finds SPACE already re-armed: the re-arm comes before the switch."""
    w = make_window().window
    w.safety.trigger('t')                                # uses up SPACE
    set_mode(w, 'DMX')
    real_select = w.output.select

    def select_then_stop(mode):
        real_select(mode)
        w.safety.trigger('during the switch')

    monkeypatch.setattr(w.output, 'select', select_then_stop)
    set_mode(w, 'MIDI')
    assert note_ons() == [[106, 112], [106, 112]]


def test_opening_a_midi_port_rearms_space(make_window):
    """Q12: SoundSwitch on a newly opened port hasn't had SPACE yet."""
    fake_rtmidi.ports.append('PyLZR-MIDI 1')
    w = make_window().window
    w.safety.trigger('t')                                # SPACE to the virtual port
    w.settings_panel.midi_port_changed.emit('PyLZR-MIDI 1')
    assert w.midi_out.port_label == 'PyLZR-MIDI 1'
    w.safety.trigger('t')
    w.safety.trigger('t')
    assert note_ons() == [[106, 112], [106, 112]]        # once per port: the third stop sends all-notes-off only


def test_dmx_mode_stop_sends_no_midi_and_keeps_space_armed(make_window):
    w = make_window().window
    set_mode(w, 'DMX')
    w.safety.trigger('t')
    assert note_messages() == []
    w.output.select('MIDI')                              # directly: nothing re-arms
    w.safety.trigger('t')
    assert note_messages() == [ALL_OFF, SPACE_ON, SPACE_OFF]    # the DMX-mode stop didn't use up the arm


def test_trigger_twice_sends_the_blackout_once_per_call(make_window, qapp):
    w = make_window().window
    set_mode(w, 'DMX')
    n = len(dmx_packets())
    w.safety.trigger('t')
    assert len(dmx_packets()) == n + 3
    w.safety.trigger('t')
    assert len(dmx_packets()) == n + 6                   # no events processed in between
    qapp.processEvents()
    assert len(dmx_packets()) == n + 9 and not w.dmx_out.active
    w.safety.trigger('t')
    assert len(dmx_packets()) == n + 9                   # DMX is off now


def test_closing_the_window_unregisters_its_stops(make_window):
    h = make_window()
    w = h.window
    h.close()
    udp_count, midi_count = len(fake_udp.sent), len(fake_rtmidi.sent)
    w.safety.trigger('x')
    assert (len(fake_udp.sent), len(fake_rtmidi.sent)) == (udp_count, midi_count)


def test_ctrl_c_in_a_slot_closes_the_window_like_the_close_button(hooks, make_window, qapp):
    stop = EmergencyStop()
    install_excepthook(stop, on_interrupt=pylzr.__main__._quit_as_if_closed)
    w = make_window(safety=stop).window
    w.show()
    set_mode(w, 'DMX')
    w.dmx_out.universe.set(1, 255)
    raise_in_a_slot(KeyboardInterrupt())
    wait_until(lambda: not w.isVisible())
    assert w.engine._is_shut_down
    assert fake_udp.sockets[0].closed == 1
    assert frames()[-3:] == DARK
    assert stop._stops == {}                             # closeEvent ran


# ── At exit, and in main() ───────────────────────────────────────────────

_ATEXIT_SCRIPT = '''
import atexit, sys
from PyQt5 import sip
from PyQt5.QtCore import QCoreApplication
from fakes import udp as fake_udp
from pylzr.core.safety import EmergencyStop
from pylzr.dmx import DMXOutput

def report():
    frames = [p[18:] for p, _ in fake_udp.sent if p[8:10] == b'\\x00\\x50']
    print('dark', sum(f == bytes(512) for f in frames[1:]))

atexit.register(report)                       # first, so it runs last
app = QCoreApplication([])
out = DMXOutput(socket_factory=fake_udp.FakeSocket)
out.universe.set(1, 255)
out.start()
stop = EmergencyStop()
stop.register('dmx', out.panic)
atexit.register(stop.trigger, 'exit')
if DELETE:
    sip.delete(out)
sys.exit(0)
'''


@pytest.mark.parametrize('delete_qt_object', [False, True], ids=['alive', 'qt_object_deleted'])
def test_atexit_blacks_out(delete_qt_object):
    code = _ATEXIT_SCRIPT.replace('DELETE', str(delete_qt_object))
    env = dict(os.environ, QT_QPA_PLATFORM='offscreen',
               PYTHONPATH=os.pathsep.join([str(ROOT / 'src'), str(ROOT / 'tests')]))
    result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'dark 3'


def test_main_installs_the_hook_and_atexit_before_any_qt_object(monkeypatch, qapp, caplog):
    events, captured = [], {}

    class StubApp:
        def __init__(self, argv):
            events.append('app')

        def exec_(self):
            return 0

    class StubWindow:
        def __init__(self, safety=None):
            events.append('window')
            captured['window_safety'] = safety

        def show(self):
            pass

    def install(stop, on_handled=None, on_interrupt=None):
        events.append('hook')
        captured.update(hook_stop=stop, on_handled=on_handled, on_interrupt=on_interrupt)

    def register(fn, *args):
        events.append('atexit')
        captured['atexit'] = (fn, args)

    monkeypatch.setattr(pylzr.__main__, 'configure_console_logging', lambda: events.append('console'))
    monkeypatch.setattr(pylzr.__main__, 'install_excepthook', install)
    monkeypatch.setattr(pylzr.__main__, 'QApplication', StubApp)
    monkeypatch.setattr(atexit, 'register', register)
    monkeypatch.setattr(pylzr.gui.style, 'apply', lambda app: None)
    monkeypatch.setattr(pylzr.gui, 'MainWindow', StubWindow)
    with pytest.raises(SystemExit):
        pylzr.__main__.main()
    assert events == ['console', 'hook', 'atexit', 'app', 'window']
    stop = captured['hook_stop']
    assert isinstance(stop, EmergencyStop) and captured['window_safety'] is stop
    fn, args = captured['atexit']
    assert fn == stop.trigger and args == ('exit',)
    assert captured['on_interrupt'] is pylzr.__main__._quit_as_if_closed
    with caplog.at_level(logging.WARNING, logger='pylzr'):
        captured['on_handled']()
    assert pylzr.__main__.KEEP_RUNNING_HINT in caplog.text


def test_quit_as_if_closed_queues_close_all_windows(monkeypatch, qapp):
    recorded = []

    class StubTimer:
        @staticmethod
        def singleShot(ms, fn):
            recorded.append((ms, fn))

    monkeypatch.setattr(pylzr.__main__, 'QTimer', StubTimer)
    pylzr.__main__._quit_as_if_closed()
    assert recorded == [(0, QApplication.closeAllWindows)]
