"""The Attributes tab through the real main window: the app's patch reaches
the tab, its values go out at each fixture's own address, tabs hand the
output over, and closing clears it (DMX goes to the fake network)."""

from helpers import dmx_packets


def frame(harness) -> bytes:
    harness.window.dmx_out._tick()
    return dmx_packets()[-1]['data']


def setup(harness, fixtures=2):
    """DMX mode, `fixtures` Gruolins patched (at 1, 37, …), the tester open on Attributes."""
    w = harness.window
    for _ in range(fixtures):
        w.settings_panel.dmx.fixtures._add_btn.click()
    w.settings_panel.set_control_mode('DMX')
    w.settings_panel.dmx._tester_btn.click()
    tester = w._dmx_tester
    tester._tabs.setCurrentWidget(tester.attributes)
    return tester, tester.attributes


def test_the_tester_has_both_tabs(harness):
    tester, _ = setup(harness, fixtures=0)
    assert tester.tabs() == ['Channels', 'Attributes']


def test_the_apps_patch_reaches_the_tab(harness):
    _, tab = setup(harness)
    assert [tab._fixture.itemText(i) for i in range(tab._fixture.count())] == ['Laser 1', 'Laser 2']


def test_values_go_out_at_the_fixtures_address(harness):
    _, tab = setup(harness)
    tab._power.setChecked(True)
    data = frame(harness)
    assert data[0] == 255 and not any(data[36:])                            # Laser 1: channels 1–36
    tab._fixture.setCurrentIndex(1)
    tab._power.setChecked(True)
    data = frame(harness)
    assert data[36] == 255 and not any(data[:36])                           # Laser 2 only: Laser 1 back to dark


def test_switching_tabs_hands_the_output_over(harness):
    tester, tab = setup(harness)
    tab._power.setChecked(True)
    assert frame(harness)[0] == 255
    tester._tabs.setCurrentWidget(tester.channels)
    assert frame(harness) == bytes(512)                                     # the channel sliders are all 0
    tester._tabs.setCurrentWidget(tab)
    assert frame(harness)[0] == 255


def test_closing_the_tester_clears_and_forgets(harness):
    tester, tab = setup(harness)
    tab._power.setChecked(True)
    tester.close()
    assert frame(harness) == bytes(512) and not harness.window.dmx_out.universe.has_overrides
    assert tab.state() == {}                                                # opening again starts unset


def test_editing_the_patch_while_the_tester_is_open(harness):
    _, tab = setup(harness)
    harness.window.settings_panel.dmx.fixtures._add_btn.click()
    assert tab._fixture.count() == 3 and tab._fixture.itemText(2) == 'Laser 3'


def test_nothing_patched_sends_nothing(harness):
    _, tab = setup(harness, fixtures=0)
    assert tab.fixture() is None and frame(harness) == bytes(512)
