from pylzr.gui import AvgPanel, LogPanel
from pylzr.gui.log_panel import _AVG_ROWS, _MAX_LOG_LINES


def test_console_drops_oldest_lines_beyond_cap(qapp):
    panel = LogPanel()
    for i in range(_MAX_LOG_LINES + 50):
        panel.append_message(f'line {i}', '')
    lines = panel._text.toPlainText().splitlines()
    assert len(lines) == _MAX_LOG_LINES
    assert lines[0] == 'line 50' and lines[-1] == f'line {_MAX_LOG_LINES + 49}'


def test_averages_panel_keeps_most_recent_rows(qapp):
    panel = AvgPanel()
    for i in range(_AVG_ROWS + 5):
        panel.append_avgs(float(i), float(i) * 10)
    lines = panel._text.toPlainText().splitlines()
    assert len(lines) == _AVG_ROWS
    # newest last, as whole numbers
    assert lines[0].split() == ['L', '5', 'H', '50']
    assert lines[-1].split()[:2] == ['L', f'{_AVG_ROWS + 4}']


def test_panels_are_cards_with_dim_titles(qapp):
    from pylzr.gui.widgets import Card
    for panel, title in ((LogPanel(), 'CONSOLE'), (AvgPanel(), 'AVERAGES')):
        assert isinstance(panel, Card)
        assert panel.title.text() == title and panel.title.property('tone') == 'dim'
        assert panel._text.height() == 130 and panel._text.property('role') == 'log'


def test_averages_are_rounded_and_right_aligned(qapp):
    panel = AvgPanel()
    panel.append_avgs(1821.75, 629.5)
    panel.append_avgs(64.2, 12345.4)
    assert panel._text.toPlainText().splitlines() == ['L  1822   H   630', 'L    64   H 12345']
