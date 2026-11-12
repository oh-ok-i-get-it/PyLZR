"""The DMX tester window and its Channels tab: what the sliders report,
start/count limits, and that only the visible tab drives the output."""

import pytest
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QWidget

from pylzr.gui import DMXTesterWindow


@pytest.fixture
def tester(qapp):
    window = DMXTesterWindow()
    yield window
    window.deleteLater()


@pytest.fixture
def channels(tester):
    """The Channels tab, where the sliders are."""
    return tester.channels


@pytest.fixture
def received(tester):
    got = []
    tester.channels_changed.connect(lambda start, values: got.append((start, values)))
    return got


def test_starts_at_channel_1_with_16_dark_channels(tester, channels):
    assert channels.start == 1 and channels.count == 16
    assert channels.values == [0] * 16
    assert [label.text() for label in channels._channel_labels][:3] == ['1', '2', '3']
    assert tester.windowFlags() & Qt.WindowType_Mask == Qt.Tool   # a tool window, not a plain one
    assert 'live' in channels.findChild(type(channels._channel_labels[0]), 'Warning').text()


def test_slider_reports_every_shown_channel(tester, received, channels):
    channels._sliders[2].setValue(200)
    assert received == [(1, [0, 0, 200] + [0] * 13)]
    assert channels._value_boxes[2].value() == 200


def test_typing_a_value_moves_the_slider_and_reports_once(tester, received, channels):
    channels._value_boxes[0].setValue(37)
    assert channels._sliders[0].value() == 37
    assert received == [(1, [37] + [0] * 15)]


def test_changing_start_renumbers_and_zeroes(tester, received, channels):
    channels._sliders[0].setValue(255)
    channels._start_box.setValue(9)
    assert received[-1] == (9, [0] * 16)          # nothing jumps onto channels 9–24
    assert channels._channel_labels[0].text() == '9'
    assert channels._channel_labels[-1].text() == '24'
    assert channels._value_boxes[0].value() == 0


def test_changing_count_keeps_shown_values(tester, received, channels):
    channels._sliders[0].setValue(10)
    channels._sliders[5].setValue(50)
    channels._count_box.setValue(4)
    assert received[-1] == (1, [10, 0, 0, 0])
    channels._count_box.setValue(8)
    assert received[-1] == (1, [10, 0, 0, 0, 0, 0, 0, 0])
    assert channels.count == 8 and len(channels._value_boxes) == 8


def test_never_runs_past_channel_512(tester, channels):
    channels._start_box.setValue(600)
    assert channels.start == 497                    # 497 + 16 - 1 = 512
    channels._count_box.setValue(32)
    assert channels.count == 16                     # can't show past 512 from 497
    channels._start_box.setValue(1)
    channels._count_box.setValue(32)
    assert channels._start_box.maximum() == 481     # 481 + 32 - 1 = 512
    channels._count_box.setValue(99)
    assert channels.count == 32                     # at most 32 shown


def test_last_channel_is_reachable(tester, received, channels):
    channels._count_box.setValue(1)
    channels._start_box.setValue(512)
    channels._sliders[0].setValue(1)
    assert received[-1] == (512, [1])


def test_all_zero(tester, received, channels):
    channels._sliders[0].setValue(100)
    channels._sliders[15].setValue(100)
    channels._zero_btn.click()
    assert received[-1] == (1, [0] * 16)
    assert all(box.value() == 0 for box in channels._value_boxes)


def test_showing_reports_the_current_values(tester, received):
    tester.show()
    assert received == [(1, [0] * 16)]


def test_closing_reports_and_reopens_dark(tester, received, channels):
    closed = []
    tester.closed.connect(lambda: closed.append(True))
    tester.show()
    channels._sliders[3].setValue(99)
    tester.close()
    assert closed == [True]
    assert channels.values == [0] * 16
    tester.show()
    assert received[-1] == (1, [0] * 16)


def test_header_labels_are_light_and_the_warning_has_its_role(tester):
    from PyQt5.QtWidgets import QLabel
    light = [lbl.text() for lbl in tester.channels.findChildren(QLabel) if lbl.property('tone') == 'light']
    assert light == ['Start channel', 'Channels']
    assert tester.channels.findChild(QLabel, 'Warning').property('role') == 'warning'


# ── Tabs ─────────────────────────────────────────────────────────────────

class FakeTab(QWidget):
    """A second tab with the tester-tab protocol: channels_changed, resend(), reset()."""

    channels_changed = pyqtSignal(int, list)

    def __init__(self, start=37, values=(1, 2, 3)):
        super().__init__()
        self.start, self.values, self.resets = start, list(values), 0

    def resend(self):
        self.channels_changed.emit(self.start, self.values)

    def reset(self):
        self.resets += 1


@pytest.fixture
def fake(tester):
    tab = FakeTab()
    tester._add_tab(tab, 'Fake')
    return tab


def test_channels_then_attributes(tester):
    assert tester.tabs() == ['Channels', 'Attributes'] and tester._current() is tester.channels


def test_only_the_visible_tab_drives_the_output(tester, received, channels, fake):
    fake.resend()                                 # hidden: nothing goes out
    assert received == []
    channels._sliders[0].setValue(9)
    assert received == [(1, [9] + [0] * 15)]


def test_switching_tabs_sends_the_new_tabs_values(tester, received, channels, fake):
    channels._sliders[0].setValue(9)
    tester._tabs.setCurrentWidget(fake)
    assert received[-1] == (37, [1, 2, 3])        # replaces the channel values
    channels._sliders[1].setValue(5)              # now hidden: nothing goes out
    assert received[-1] == (37, [1, 2, 3])
    tester._tabs.setCurrentWidget(channels)
    assert received[-1] == (1, [9, 5] + [0] * 14)


def test_showing_sends_the_visible_tab(tester, received, fake):
    tester._tabs.setCurrentWidget(fake)
    received.clear()
    tester.show()
    assert received == [(37, [1, 2, 3])]


def test_closing_puts_every_tab_back_to_dark(tester, channels, fake):
    tester.show()
    channels._sliders[0].setValue(50)
    tester.close()
    assert channels.values == [0] * 16 and fake.resets == 1


def test_styled_window_keeps_the_page_as_it_was(styled_app):
    from pylzr.gui import style
    window = DMXTesterWindow()
    window.show()
    assert all(f'QTabBar::tab{state}' in style.stylesheet() for state in ('', ':hover', ':selected'))
    assert window._tabs.tabBar().isVisible() and window.tabs() == ['Channels', 'Attributes']
    assert min(slider.height() for slider in window.channels._sliders) >= 140   # the faders keep their length
    window.close()
    window.deleteLater()
