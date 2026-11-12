"""The tester's Attributes tab (gui/attribute_tester.py) on its own.

The tests marked 'any laser' run on two very different lasers, the shipped
Gruolin (two layers, power channel, group + number patterns) and the
EL-400 (tests/el400.py: one layer, no power channel, mode + selection
patterns), to show the tab is built from the fixture, not for one laser."""

import el400
import pytest
from PyQt5.QtCore import QPoint, QPointF, Qt
from PyQt5.QtGui import QWheelEvent
from shipped import GRUOLIN, renderer

from pylzr.fixtures import AttrKey, Kind, Patch, PatchEntry, PatternEntry, PatternRequest, Rig, compile_fixture
from pylzr.fixtures.mappings import OFF_CHOICES
from pylzr.gui import AttributeTester
from pylzr.gui.attribute_tester import EXTRAS_CARD, attribute_label

LASERS = {
    'gruolin': (GRUOLIN, renderer),
    'el400':   (el400.KEY, el400.renderer),
}


def make_rig(*entries, renderers=None):
    renderers = renderers or {GRUOLIN: renderer(), el400.KEY: el400.renderer()}
    return Rig(Patch(tuple(PatchEntry(*e) for e in entries)), renderers)


def tagged_gruolin():
    base = renderer().resolved
    library = base.binding.patterns.with_entry(
        PatternEntry('tunnel 3', {'Pattern Group': 64, 'Pattern Selection': 15}, 'tunnel', {'energy': 0.8}))
    library = library.with_entry(PatternEntry('calm line', {'Pattern Group': 0, 'Pattern Selection': 6}, 'line'))
    return compile_fixture(base.binding.with_patterns(library), base.profile)


@pytest.fixture
def tab(qapp):
    widget = AttributeTester()
    yield widget
    widget.deleteLater()


@pytest.fixture
def sent(tab):
    got = []
    tab.channels_changed.connect(lambda start, values: got.append((start, values)))
    return got


@pytest.fixture(params=list(LASERS))
def laser(request, tab):
    """Any laser: the tab driving one fixture of that type at address 10."""
    key, make = LASERS[request.param]
    tab.set_rig(make_rig(('Laser', key, 10)))
    return make()


@pytest.fixture
def gruolins(tab):
    rig = make_rig(('Laser L', GRUOLIN, 1), ('Laser R', GRUOLIN, 37))
    tab.set_rig(rig)
    return rig


def expected(tab, rig, state, raw=None):
    """What the tab should send for the chosen fixture with `state`."""
    start, result = rig.render_fixture(tab.fixture(), state, raw or {})
    return start, list(result.values)


# ── Built from the fixture (any laser) ───────────────────────────────────

def test_a_row_for_every_attribute_the_fixture_supports(tab, laser):
    shown = [name for names in tab.card_rows().values() for name in names]
    wanted = [a.name for a in laser.attributes if a.kind != Kind.EVENT and a.name != 'power'
              and any(laser.supports(AttrKey(a.name, layer)) for layer in laser.layers)]
    assert sorted(shown) == sorted(wanted) and len(shown) == len(set(shown))
    extras = [a.name for a in laser.attributes if a.is_extra and a.name in wanted]
    assert tab.card_rows().get(EXTRAS_CARD, []) == extras


def test_one_column_per_layer(tab, laser):
    titles = [t.text() for t in tab._layer_titles]
    assert titles == [f'LAYER {layer.upper()}' for layer in laser.layers]
    assert set(tab._patterns) == set(laser.layers)


def test_dropdowns_offer_only_this_fixtures_choices(tab, laser):
    for key, cell in tab._cells.items():
        attribute = laser.attributes[key.name]
        if attribute.kind != Kind.OPTION:
            continue
        items = [cell.combo.itemData(i) for i in range(cell.combo.count())]
        assert items[0] is None                                             # '—': unset
        assert items[1:] == [o for o in attribute.options if o in laser.choices(key) or o in OFF_CHOICES]


def test_power_toggle_only_when_the_fixture_has_power(tab, laser):
    assert tab._power.isVisibleTo(tab) == laser.supports('power')


def test_every_control_sends_exactly_what_the_renderer_makes(tab, laser, sent):
    rig = tab._rig
    state = {}
    for key, cell in list(tab._cells.items()):
        if hasattr(cell, 'slider'):
            cell.slider.setValue(70)
            state[str(key)] = 0.7
        else:
            cell.combo.setCurrentIndex(cell.combo.count() - 1)
            state[str(key)] = cell.combo.currentData()
        assert sent[-1] == expected(tab, rig, state)
    assert tab.state() == state


def test_untagged_pattern_sends_raw_values(tab, laser, sent):
    cell = tab.pattern_cell('a')
    cell.source.setCurrentIndex(3)                                          # Untagged
    raw = tab.raw_patterns()['a']
    assert set(raw) == {channel.name for channel in laser.pattern_channels('a')}
    assert sent[-1] == expected(tab, tab._rig, {}, {'a': raw})
    name, (segments, spin) = next(iter(cell.raw_parts.items()))
    segments.setCurrentIndex(segments.count() - 1)                          # the last segment, at its start
    last = laser.pattern_channels('a')[0].segments[-1]
    assert tab.raw_patterns()['a'][name] == last.start == spin.value()
    assert (spin.minimum(), spin.maximum()) == (last.start, last.end)
    assert sent[-1] == expected(tab, tab._rig, {}, tab.raw_patterns())
    cell.source.setCurrentIndex(0)
    assert tab.raw_patterns() == {} and sent[-1] == expected(tab, tab._rig, {})


# ── Values, unset and snapping (Gruolin) ─────────────────────────────────

def test_untouched_controls_are_unset(tab, gruolins, sent):
    assert tab.state() == {} and tab.cell('size').readout.text() == '—'
    assert tab.cell('color').value() is None
    tab.cell('size').slider.setValue(45)
    assert tab.cell('size').readout.text() == '45%' and tab.state() == {'size': 0.45}
    tab.cell('color').combo.setCurrentIndex(0)                              # back to '—'
    assert 'color' not in tab.state()


@pytest.mark.parametrize('position, shown, value', [
    (2, '0%', 0.0), (-3, '0%', 0.0), (4, '+4%', 0.04), (-50, '-50%', -0.5), (100, '+100%', 1.0),
])
def test_bipolar_sliders_snap_to_the_centre(tab, gruolins, position, shown, value):
    cell = tab.cell('pos_x@b')
    cell.slider.setValue(position)
    assert cell.readout.text() == shown and tab.state()['pos_x@b'] == value


def test_ignored_settings_are_marked(tab, gruolins):
    tab.cell('rot_z').slider.setValue(20)
    assert tab.cell('rot_z').readout.text() == '20%'
    tab.cell('spin_z').slider.setValue(40)                                  # spin wins the shared channel
    assert tab.cell('rot_z').readout.text() == 'ignored'
    assert tab.cell('rot_z').readout.property('state') == 'ignored'
    tab.cell('spin_z').slider.setValue(1)                                   # snaps to 0: hands the channel back
    assert tab.cell('rot_z').readout.text() == '20%'


def test_power(tab, gruolins, sent):
    tab._power.setChecked(True)
    assert tab._power.text() == 'ON' and tab.state() == {'power': 'on'}
    assert sent[-1] == expected(tab, gruolins, {'power': 'on'})
    tab._power.setChecked(False)
    assert tab.state() == {'power': 'off'}


# ── Patterns (Gruolin) ───────────────────────────────────────────────────

def test_without_tags_only_none_and_untagged_can_be_chosen(tab, gruolins):
    model = tab.pattern_cell('a').source.model()
    assert [model.item(i).isEnabled() for i in range(4)] == [True, False, False, True]
    assert tab.pattern_cell('a').matched.text() == 'No pattern: this layer is dark.'


@pytest.fixture
def tagged(tab):
    rig = make_rig(('Laser L', GRUOLIN, 1), renderers={GRUOLIN: tagged_gruolin()})
    tab.set_rig(rig)
    return rig


def test_pattern_by_category_and_scales(tab, tagged, sent):
    cell = tab.pattern_cell('b')
    cell.source.setCurrentIndex(1)
    cell.category.setCurrentIndex(cell.category.findData('tunnel'))
    cell.levels['energy'].setCurrentIndex(4)                                # ('any', 1, …): level 4 → 0.8
    assert tab.state() == {'pattern@b': PatternRequest.of('tunnel', energy=0.8)}
    assert cell.matched.text() == 'Matched: tunnel 3'
    assert sent[-1][1][19:21] == [64, 15]
    assert cell.category.itemText(cell.category.findData('tunnel')) == 'tunnel (1)'
    cell.category.setCurrentIndex(cell.category.findData('star'))
    assert cell.matched.text() == 'Nothing tagged in this category' and sent[-1][1][19:21] == [0, 0]


def test_pattern_by_name(tab, tagged, sent):
    cell = tab.pattern_cell('a')
    cell.source.setCurrentIndex(2)
    cell.entry.setCurrentIndex(cell.entry.findData('calm line'))
    assert tab.state() == {'pattern': PatternRequest.entry('calm line')}
    assert cell.matched.text() == 'Matched: calm line' and sent[-1][1][2:4] == [0, 6]


def test_an_untagged_pick_that_is_tagged_says_so(tab, tagged):
    cell = tab.pattern_cell('a')
    cell.source.setCurrentIndex(3)
    group, group_value = cell.raw_parts['Pattern Group']
    group.setCurrentIndex(4)                                                # Animation patterns, 64
    cell.raw_parts['Pattern Selection'][1].setValue(15)
    assert cell.matched.text() == 'Tagged as tunnel 3 (tunnel)'


# ── Fixtures, Reset and the tab protocol ─────────────────────────────────

def test_each_fixture_keeps_its_settings(tab, gruolins, sent):
    tab.cell('size').slider.setValue(60)
    assert sent[-1][0] == 1
    tab._fixture.setCurrentIndex(1)                                         # Laser R
    assert tab.fixture() == 'Laser R' and tab.state() == {}
    assert sent[-1] == expected(tab, gruolins, {})                          # sends its own values, at 37
    assert sent[-1][0] == 37
    tab._fixture.setCurrentIndex(0)
    assert tab.state() == {'size': 0.6} and tab.cell('size').value() == 0.6


def test_reset_button_clears_this_fixture(tab, gruolins, sent):
    tab.cell('size').slider.setValue(60)
    tab._fixture.setCurrentIndex(1)
    tab.cell('size@b').slider.setValue(10)
    tab._reset_btn.click()
    assert tab.state() == {} and sent[-1] == expected(tab, gruolins, {})
    tab._fixture.setCurrentIndex(0)
    assert tab.state() == {'size': 0.6}                                     # the other one keeps its settings


def test_reset_clears_every_fixture_without_sending(tab, gruolins, sent):
    tab.cell('size').slider.setValue(60)
    count = len(sent)
    tab.reset()
    assert len(sent) == count and tab.state() == {} and tab.cell('size').readout.text() == '—'


def test_a_new_patch_keeps_what_still_fits(tab, gruolins):
    tab.cell('size').slider.setValue(60)
    tab._fixture.setCurrentIndex(1)
    tab.cell('size').slider.setValue(30)
    tab.set_rig(make_rig(('Laser L', GRUOLIN, 100), ('Laser R', el400.KEY, 37), ('New', GRUOLIN, 200)))
    assert tab.fixture() == 'Laser R' and tab.state() == {}                 # retyped: starts again
    tab._fixture.setCurrentIndex(0)
    assert tab.fixture() == 'Laser L' and tab.state() == {'size': 0.6}      # moved, same type: kept
    assert [tab._fixture.itemText(i) for i in range(tab._fixture.count())] == ['Laser L', 'Laser R', 'New']
    tab.set_rig(make_rig(('New', GRUOLIN, 200)))
    assert tab.fixture() == 'New'                                           # the chosen one is gone


def test_nothing_patched(tab, sent):
    assert tab.fixture() is None and tab._empty.isVisibleTo(tab) and not tab._scroll.isVisibleTo(tab)
    tab.resend()
    assert sent == [(1, [])]                                                # clears the override layer
    tab.set_rig(make_rig(('Laser', GRUOLIN, 1)))
    assert tab.fixture() == 'Laser' and not tab._empty.isVisibleTo(tab)
    tab.set_rig(make_rig())
    assert tab.fixture() is None and tab._empty.isVisibleTo(tab)


def test_set_rig_sends_only_while_shown(tab, sent):
    tab.set_rig(make_rig(('Laser', GRUOLIN, 1)))
    assert sent == []
    tab.show()
    tab.set_rig(make_rig(('Laser', GRUOLIN, 5)))
    assert sent[-1][0] == 5
    tab.hide()


def test_scrolling_over_a_control_does_not_change_it(tab, gruolins):
    slider = tab.cell('size').slider
    event = QWheelEvent(QPointF(5, 5), QPointF(5, 5), QPoint(0, 0), QPoint(0, 120), Qt.NoButton, Qt.NoModifier,
                        Qt.NoScrollPhase, False)
    slider.wheelEvent(event)
    assert slider.value() == 0 and not event.isAccepted() and tab.state() == {}


def test_labels():
    assert [attribute_label(n) for n in ('pos_x', 'color_effect', 'x_flowing_water', 'x_zoom_pulse_2')] == \
        ['Pos X', 'Color effect', 'Flowing water', 'Zoom pulse 2']
