import pytest
from PyQt5.QtCore import Qt

from pylzr.gui import DMXTesterWindow


@pytest.fixture
def tester(qapp):
    window = DMXTesterWindow()
    yield window
    window.deleteLater()


@pytest.fixture
def received(tester):
    got = []
    tester.channels_changed.connect(lambda start, values: got.append((start, values)))
    return got


def test_starts_at_channel_1_with_16_dark_channels(tester):
    assert tester.start == 1 and tester.count == 16
    assert tester.values == [0] * 16
    assert [label.text() for label in tester._channel_labels][:3] == ['1', '2', '3']
    assert tester.windowFlags() & Qt.WindowType_Mask == Qt.Tool   # a tool window, not a plain one
    assert 'live' in tester.findChild(type(tester._channel_labels[0]), 'Warning').text()


def test_slider_reports_every_shown_channel(tester, received):
    tester._sliders[2].setValue(200)
    assert received == [(1, [0, 0, 200] + [0] * 13)]
    assert tester._value_boxes[2].value() == 200


def test_typing_a_value_moves_the_slider_and_reports_once(tester, received):
    tester._value_boxes[0].setValue(37)
    assert tester._sliders[0].value() == 37
    assert received == [(1, [37] + [0] * 15)]


def test_changing_start_renumbers_and_zeroes(tester, received):
    tester._sliders[0].setValue(255)
    tester._start_box.setValue(9)
    assert received[-1] == (9, [0] * 16)          # nothing jumps onto channels 9–24
    assert tester._channel_labels[0].text() == '9'
    assert tester._channel_labels[-1].text() == '24'
    assert tester._value_boxes[0].value() == 0


def test_changing_count_keeps_shown_values(tester, received):
    tester._sliders[0].setValue(10)
    tester._sliders[5].setValue(50)
    tester._count_box.setValue(4)
    assert received[-1] == (1, [10, 0, 0, 0])
    tester._count_box.setValue(8)
    assert received[-1] == (1, [10, 0, 0, 0, 0, 0, 0, 0])
    assert tester.count == 8 and len(tester._value_boxes) == 8


def test_never_runs_past_channel_512(tester):
    tester._start_box.setValue(600)
    assert tester.start == 497                    # 497 + 16 - 1 = 512
    tester._count_box.setValue(32)
    assert tester.count == 16                     # can't show past 512 from 497
    tester._start_box.setValue(1)
    tester._count_box.setValue(32)
    assert tester._start_box.maximum() == 481     # 481 + 32 - 1 = 512
    tester._count_box.setValue(99)
    assert tester.count == 32                     # at most 32 shown


def test_last_channel_is_reachable(tester, received):
    tester._count_box.setValue(1)
    tester._start_box.setValue(512)
    tester._sliders[0].setValue(1)
    assert received[-1] == (512, [1])


def test_all_zero(tester, received):
    tester._sliders[0].setValue(100)
    tester._sliders[15].setValue(100)
    tester._zero_btn.click()
    assert received[-1] == (1, [0] * 16)
    assert all(box.value() == 0 for box in tester._value_boxes)


def test_showing_reports_the_current_values(tester, received):
    tester.show()
    assert received == [(1, [0] * 16)]


def test_closing_reports_and_reopens_dark(tester, received):
    closed = []
    tester.closed.connect(lambda: closed.append(True))
    tester.show()
    tester._sliders[3].setValue(99)
    tester.close()
    assert closed == [True]
    assert tester.values == [0] * 16
    tester.show()
    assert received[-1] == (1, [0] * 16)
