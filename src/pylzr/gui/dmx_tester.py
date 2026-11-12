from PyQt5.QtWidgets import QTabWidget, QVBoxLayout, QWidget
from PyQt5.QtCore import Qt, pyqtSignal

from . import style
from .attribute_tester import AttributeTester
from .channel_tester import ChannelTester

TAB_GAP    = 10   # between the tab bar's line and the page
TAB_HEIGHT = 36   # what the tab bar adds to the window (its height + the gap under it)
HEIGHT     = 600  # room for the Attributes grid (the Channels faders just get longer)


class DMXTesterWindow(QWidget):
    """A small tool window for trying out fixtures, one tab per way of
    testing: Channels (one slider per DMX channel, `channels`) and
    Attributes (a patched fixture through its binding, `attributes`; give it
    the patch with attributes.set_rig()).

    Knows nothing about DMX output: it only reports what the visible tab
    shows. Each tab has a channels_changed(int, list) signal, resend() and
    reset() (see ChannelTester); only the visible tab's values come out, and
    switching tabs sends the new tab's values (they replace the old ones).

    Signals:
        channels_changed(int, list) — first channel (1–512) and the values
                                      (0–255) the visible tab drives; emitted
                                      on any change, when shown and when the
                                      tab changes
        closed()                    — the window was closed (every tab is then
                                      back at 0 for next time)
    """

    channels_changed = pyqtSignal(int, list)
    closed           = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent, Qt.Tool)
        self.setObjectName('DMXTester')
        self.setWindowTitle('DMX Channel Tester')
        style.dark_title_bar(self)                 # Windows only; no-op elsewhere

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(0)

        self._tabs = QTabWidget()
        self._tabs.currentChanged.connect(lambda _index: self._current().resend())
        root.addWidget(self._tabs)

        self.channels = ChannelTester()
        self._add_tab(self.channels, 'Channels')
        self.attributes = AttributeTester()
        self._add_tab(self.attributes, 'Attributes')

        self.resize(self.channels.sizeHint().width() + 24, HEIGHT)

    def _add_tab(self, tab: QWidget, title: str):
        tab.setContentsMargins(0, TAB_GAP, 0, 0)  # room between the tab bar's line and the page
        tab.channels_changed.connect(lambda start, values, tab=tab: self._forward(tab, start, values))
        self._tabs.addTab(tab, title)

    def _current(self) -> QWidget:
        return self._tabs.currentWidget()

    def _forward(self, tab: QWidget, start: int, values: list):
        if tab is self._current():                 # a hidden tab never drives the output
            self.channels_changed.emit(start, values)

    def tabs(self) -> list[str]:
        """The tab titles, in order."""
        return [self._tabs.tabText(i) for i in range(self._tabs.count())]

    # ── Qt events ─────────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        self._current().resend()                   # whoever listens starts from what's shown

    def closeEvent(self, event):
        for i in range(self._tabs.count()):
            self._tabs.widget(i).reset()           # opening again starts dark
        super().closeEvent(event)
        self.closed.emit()
