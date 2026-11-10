"""Control Mode, DMX output, the node settings and the channel tester, through
the real main window (DMX goes to the fake network, see conftest)."""

import pytest
from PyQt5.QtCore import Qt

from fakes import udp as fake_udp
from helpers import artpollreply, dmx_packets, note_ons, tone_chunks, wait_for_note_offs, wait_until
from pylzr.core import AVG_COUNT_RATE_DEFAULT
from pylzr.dmx import build_artpoll
from pylzr.gui.settings_store import DEFAULTS, SettingsStore

DEFAULT_NODE = ('10.201.6.100', 6454)


def set_mode(harness, mode):
    harness.window.settings_panel.set_control_mode(mode)


def set_node(harness, ip, port_address):
    harness.window.settings_panel.dmx.set_node(ip, port_address)


def frames():
    return [p['data'] for p in dmx_packets()]


def one_cue_of_loud_audio(harness):
    """Turn sound mode on and play one averaging window of loud bass + treble,
    which makes sound mode send a cue."""
    harness.key(Qt.Key_Shift)
    harness.feed(tone_chunks(AVG_COUNT_RATE_DEFAULT, (60, 20000), (8000, 20000)))


# ── Starting up ──────────────────────────────────────────────────────────

def test_starts_in_midi_mode_sending_no_dmx(harness):
    w = harness.window
    assert w.output.active == 'MIDI'
    assert not w.dmx_out.active
    assert fake_udp.sent == []
    assert not w.settings_panel.dmx._tester_btn.isEnabled()
    assert w.settings_panel._dmx_val.text() == 'Off'


# ── Switching mode ───────────────────────────────────────────────────────

def test_dmx_mode_sends_to_the_node_and_shows_status(harness):
    w = harness.window
    set_mode(harness, 'DMX')
    assert w.output.active == 'DMX' and w.dmx_out.active
    assert dmx_packets()[0]['to'] == DEFAULT_NODE
    assert w.settings_panel._dmx_val.text() == 'via 10.201.6.50'
    assert w.settings_panel.dmx._tester_btn.isEnabled()
    wait_until(lambda: len(dmx_packets()) >= 3)          # keeps streaming


def test_cues_go_only_to_the_chosen_output(harness):
    set_mode(harness, 'DMX')
    harness.key(Qt.Key_Q)                                # keyboard cue
    one_cue_of_loud_audio(harness)                       # sound-mode cue
    assert note_ons() == []                              # MIDI got nothing

    harness.key(Qt.Key_Shift)                            # sound mode off
    set_mode(harness, 'MIDI')
    harness.key(Qt.Key_Q)
    wait_for_note_offs()
    assert note_ons() == [[73, 112]]                     # MIDI works again


def test_sound_mode_cues_reach_midi_in_midi_mode(harness):
    """Control for the test above: the same audio does send a cue over MIDI."""
    one_cue_of_loud_audio(harness)
    assert len(note_ons()) == 1


def test_leaving_dmx_blacks_out_then_stops(harness, qapp):
    w = harness.window
    set_mode(harness, 'DMX')
    w.dmx_out.universe.set(1, 255)
    w.dmx_out._tick()
    set_mode(harness, 'MIDI')
    assert frames()[-1] == bytes(512)
    sent = len(fake_udp.sent)
    qapp.processEvents()
    assert len(fake_udp.sent) == sent and not w.dmx_out.active
    assert w.settings_panel._dmx_val.text() == 'Off'
    assert not w.settings_panel.dmx._tester_btn.isEnabled()


# ── Node settings ────────────────────────────────────────────────────────

def test_changing_the_node_redirects_packets_and_is_saved(harness):
    set_mode(harness, 'DMX')
    set_node(harness, '10.201.6.101', [0, 1, 2])
    latest = dmx_packets()[-1]
    assert latest['to'] == ('10.201.6.101', 6454)
    assert latest['sub_uni'] == 0x12
    store = SettingsStore()
    assert store.get('dmx/node_ip') == '10.201.6.101'
    assert store.get('dmx/port_address') == [0, 1, 2]


def test_mode_node_and_universe_are_restored_after_restart(make_window):
    first = make_window()
    set_node(first, '10.201.6.101', [0, 0, 3])
    set_mode(first, 'DMX')
    first.close()
    fake_udp.sent.clear()

    w = make_window().window
    assert w.output.active == 'DMX' and w.dmx_out.active
    assert w.settings_panel._mode_combo.currentData() == 'DMX'
    assert w.settings_panel.dmx._node_ip_edit.text() == '10.201.6.101'
    assert {(p['to'], p['sub_uni']) for p in dmx_packets()} == {(('10.201.6.101', 6454), 3)}  # never the default


def test_unusable_saved_node_falls_back_to_default(make_window):
    SettingsStore().set('dmx/node_ip', 'not an ip')
    SettingsStore().set('app/control_mode', 'DMX')
    make_window()
    assert dmx_packets()[0]['to'] == DEFAULT_NODE


def test_reset_returns_to_midi_and_the_default_node(harness):
    w = harness.window
    set_node(harness, '10.201.6.101', [1, 2, 3])
    set_mode(harness, 'DMX')
    w.settings_panel._reset_btn.click()
    assert w.output.active == 'MIDI' and not w.dmx_out.active
    assert frames()[-1] == bytes(512)
    assert (w.dmx_out.node_ip, str(w.dmx_out.port)) == ('10.201.6.100', '0:0:0')
    store = SettingsStore()
    assert {key: store.get(key) for key in DEFAULTS} == DEFAULTS


# ── Channel tester ───────────────────────────────────────────────────────

def open_tester(harness):
    harness.window.settings_panel.dmx._tester_btn.click()
    return harness.window._dmx_tester


def test_tester_values_go_out_live_and_clear_on_close(harness):
    w = harness.window
    set_mode(harness, 'DMX')
    tester = open_tester(harness)
    assert tester.isVisible()
    tester._start_box.setValue(5)
    tester._sliders[0].setValue(200)
    w.dmx_out._tick()
    assert frames()[-1][4] == 200                        # channel 5
    tester.close()
    w.dmx_out._tick()
    assert frames()[-1] == bytes(512)


def test_tester_is_one_window(harness):
    set_mode(harness, 'DMX')
    assert open_tester(harness) is open_tester(harness)


def test_leaving_dmx_closes_the_tester(harness):
    set_mode(harness, 'DMX')
    tester = open_tester(harness)
    tester._sliders[0].setValue(255)
    set_mode(harness, 'MIDI')
    assert not tester.isVisible()
    assert not harness.window.dmx_out.universe.has_overrides


# ── Shutdown ─────────────────────────────────────────────────────────────

def test_closing_the_app_blacks_out_and_releases_the_socket(harness):
    w = harness.window
    set_mode(harness, 'DMX')
    w.dmx_out.universe.set(1, 255)
    harness.close()
    assert frames()[-1] == bytes(512)
    assert fake_udp.sockets[0].closed == 1               # the sending socket


def test_closing_the_app_closes_the_tester(harness):
    set_mode(harness, 'DMX')
    tester = open_tester(harness)
    harness.window.close()
    assert not tester.isVisible()


def test_closing_in_midi_mode_sends_no_dmx(harness):
    harness.close()
    assert fake_udp.sent == []


@pytest.mark.parametrize('mode', ['MIDI', 'DMX'])
def test_control_mode_logged(harness, mode):
    set_mode(harness, 'DMX' if mode == 'MIDI' else 'MIDI')
    set_mode(harness, mode)
    log = harness.window.log_panel._text.toPlainText()
    assert f'Control mode: {mode}' in log
    assert 'not yet implemented' not in log


# ── Node answers ─────────────────────────────────────────────────────────

def test_node_that_answers_turns_the_indicator_green(harness):
    w = harness.window
    set_mode(harness, 'DMX')
    assert ('10.201.6.100', 6454) in [to for data, to in fake_udp.sent if data == build_artpoll()]   # asked
    fake_udp.arrive(artpollreply(), '10.201.6.100')
    wait_until(lambda: w.settings_panel._dmx_val.toolTip() == 'CR011R answered · via 10.201.6.50')
    assert w.dmx_out.state == 'connected'


def test_closing_the_app_stops_listening(harness):
    set_mode(harness, 'DMX')
    harness.close()
    listener = next(s for s in fake_udp.sockets if s.bound_to == ('', 6454))
    assert listener.closed == 1


# ── Find ─────────────────────────────────────────────────────────────────

def find(harness):
    """Show the window (offscreen) and its settings, as a user would, and click Find."""
    w = harness.window
    w.show()
    w._toggle_settings()
    assert w.settings_panel.isVisible()
    w.settings_panel.dmx._find_btn.click()
    return w


def test_find_asks_every_network_and_the_set_node(harness):
    w = find(harness)
    polls = [to for data, to in fake_udp.sent if data == build_artpoll()]
    assert polls == [('10.255.255.255', 6454), ('10.201.6.100', 6454)]
    assert not w.settings_panel.dmx._find_btn.isEnabled()          # searching
    assert dmx_packets() == []                   # finding sends no DMX (MIDI mode)


def test_picking_a_found_node_configures_and_saves_it(harness):
    w = find(harness)
    fake_udp.arrive(artpollreply(ip='10.201.6.120', subnet=1, sw_out=(4,)), '10.201.6.120')
    w.discovery._finish_search()
    dmx = w.settings_panel.dmx
    assert dmx._find_btn.isEnabled()
    [action] = dmx._nodes_menu.actions()
    assert action.text() == 'CR011R · 10.201.6.120 · 0:1:4'
    action.trigger()
    assert (w.dmx_out.node_ip, str(w.dmx_out.port)) == ('10.201.6.120', '0:1:4')
    store = SettingsStore()
    assert (store.get('dmx/node_ip'), store.get('dmx/port_address')) == ('10.201.6.120', [0, 1, 4])
    assert 'DMX: found CR011R · 10.201.6.120 · 0:1:4' in w.log_panel._text.toPlainText()


def test_nothing_found_logs_what_to_check(harness):
    w = find(harness)
    w.discovery._finish_search()
    assert 'no Art-Net nodes answered' in w.log_panel._text.toPlainText()
    assert [a.text() for a in w.settings_panel.dmx._nodes_menu.actions()] == [
        'No Art-Net nodes answered (see the log)']


def test_settings_closed_during_the_search_shows_no_menu(harness):
    w = find(harness)
    w._toggle_settings()                         # closed
    fake_udp.arrive(artpollreply(), '10.201.6.100')
    w.discovery._finish_search()
    assert w.settings_panel.dmx._nodes_menu is None
    assert w.settings_panel.dmx._find_btn.isEnabled()
    assert 'DMX: found CR011R · 10.201.6.100 · 0:0:0' in w.log_panel._text.toPlainText()


def test_search_ends_by_itself_in_the_app(harness):
    w = find(harness)
    w.discovery._search_timer.setInterval(10)    # instead of 2 s
    w.discovery._search_timer.start()
    wait_until(lambda: w.settings_panel.dmx._find_btn.isEnabled())
