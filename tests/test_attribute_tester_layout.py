"""The Attributes tab with PyLZR's real fonts and stylesheet, in the
tester window at its real size: names and readouts aren't cut, the layer
columns are equal and sit under their titles, on both test lasers."""

import el400
import pytest
from PyQt5.QtWidgets import QApplication, QLabel
from shipped import GRUOLIN, renderer

from pylzr.fixtures import Patch, PatchEntry, Rig
from pylzr.gui import DMXTesterWindow
from pylzr.gui.attribute_tester import LABEL_W, READOUT_W, attribute_label


@pytest.fixture(params=['gruolin', 'el400'])
def shown(request, styled_app):
    key, make = {'gruolin': (GRUOLIN, renderer), 'el400': (el400.KEY, el400.renderer)}[request.param]
    window = DMXTesterWindow()
    window.attributes.set_rig(Rig(Patch((PatchEntry('Laser', key, 1),)), {key: make()}))
    window.show()
    window._tabs.setCurrentWidget(window.attributes)
    QApplication.processEvents()
    yield window, window.attributes, make()
    window.close()
    window.deleteLater()


def x(widget, tab):
    return widget.mapTo(tab, widget.rect().topLeft()).x()


def test_names_fit_their_column(shown):
    _, tab, _ = shown
    names = [lbl for lbl in tab._scroll.widget().findChildren(QLabel) if lbl.width() == LABEL_W]
    shown_names = {attribute_label(n) for rows in tab.card_rows().values() for n in rows}
    assert {lbl.text() for lbl in names} == shown_names                     # one label per row, as drawn
    for lbl in names:
        assert lbl.fontMetrics().horizontalAdvance(lbl.text()) <= LABEL_W, lbl.text()


def test_readouts_fit(shown):
    _, tab, _ = shown
    slider = next(c for c in tab._cells.values() if hasattr(c, 'readout'))
    metrics = slider.readout.fontMetrics()
    assert max(metrics.horizontalAdvance(t) for t in ('+100%', '-100%', 'ignored')) <= READOUT_W - 2


def test_columns_are_equal_and_under_their_titles(shown):
    window, tab, laser = shown
    assert len(tab._layer_titles) == len(laser.layers)
    for layer, title in zip(laser.layers, tab._layer_titles, strict=True):
        cell = tab.pattern_cell(layer)
        assert abs(x(title, tab) - x(cell, tab)) <= 1, layer
    if len(laser.layers) == 2:
        a, b = (tab.pattern_cell(layer).width() for layer in laser.layers)
        assert abs(a - b) <= 1
    viewport = tab._scroll.viewport()
    for cell in tab._cells.values():
        assert cell.mapTo(viewport, cell.rect().topRight()).x() <= viewport.width()   # nothing runs off the side
