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
    # newest last; plain text collapses the HTML padding, so compare tokens
    assert lines[0].split() == ['L', '5.0000', 'H', '50.0000']
    assert lines[-1].split()[:2] == ['L', f'{_AVG_ROWS + 4}.0000']
