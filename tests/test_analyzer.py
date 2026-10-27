import pytest

from pylzr.analysis import AudioAnalyzer


def test_returns_none_until_window_is_full():
    analyzer = AudioAnalyzer(count_rate=4)
    assert [analyzer.push(1.0, 1.0) for _ in range(3)] == [None, None, None]
    assert analyzer.push(1.0, 1.0) is not None


def test_window_average_scaling():
    # low is scaled x1000 and high x10000, both averaged over the window
    analyzer = AudioAnalyzer(count_rate=4)
    for low, high in [(0.1, 0.01), (0.2, 0.02), (0.3, 0.03)]:
        analyzer.push(low, high)
    low_avg, high_avg = analyzer.push(0.4, 0.04)
    assert low_avg == pytest.approx((0.1 + 0.2 + 0.3 + 0.4) / 4 * 1000)
    assert high_avg == pytest.approx((0.01 + 0.02 + 0.03 + 0.04) / 4 * 10000)


def test_windows_do_not_overlap():
    analyzer = AudioAnalyzer(count_rate=2)
    analyzer.push(1.0, 1.0)
    assert analyzer.push(1.0, 1.0) == pytest.approx((1000.0, 10000.0))
    analyzer.push(0.0, 0.0)
    assert analyzer.push(0.0, 0.0) == pytest.approx((0.0, 0.0))


def test_changing_count_rate_discards_partial_window():
    analyzer = AudioAnalyzer(count_rate=4)
    analyzer.push(9.0, 9.0)
    analyzer.count_rate = 2
    assert analyzer.count_rate == 2
    assert analyzer.push(1.0, 1.0) is None
    assert analyzer.push(1.0, 1.0) == pytest.approx((1000.0, 10000.0))
