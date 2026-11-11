"""Golden renders of the shipped Gruolin binding: each named state below and
the 36 channel values it sends, stored in tests/golden/gruolin_renders.json
(split for reading: channels 1–2, then layer a's 3–19 and layer b's 20–36)
and compared exactly. A change to the binding, the profile or the renderer
that alters what the laser receives shows up here, value by value.

If a change is MEANT to alter the output, regenerate and review the diff:

    PYLZR_UPDATE_GOLDEN=1 pytest tests/test_gruolin_renders.py
"""

import json
import os
from pathlib import Path

import pytest
from shipped import renderer

from pylzr.fixtures.jsonio import dumps

GOLDEN = Path(__file__).parent / 'golden' / 'gruolin_renders.json'

STATES = {
    'nothing set':              {},
    'power on':                 {'power': 'on'},
    'power off':                {'power': 'off'},
    'size smallest':            {'size': 0.0},
    'size half':                {'size': 0.5},
    'size largest':             {'size': 1.0},
    'position corners':         {'pos_x': -1.0, 'pos_y': 1.0},
    'position a little':        {'pos_x': 0.25, 'pos_y': -0.25},
    'every colour a b':         {'color': 'cyan', 'color@b': 'original'},
    'colour jump forwards':     {'color_effect': 'jump', 'color_speed': 0.5},
    'colour gradient backwards': {'color_effect': 'gradient', 'color_speed': -0.5},
    'flowing water 25':         {'x_flowing_water': 'water_25', 'color': 'red'},
    'rgb change':               {'x_color_change': 'rgb'},
    'line scan':                {'scan_speed': 0.5},
    'dot scan':                 {'draw_style': 'dots', 'scan_speed': 0.5},
    'bright scan':              {'x_bright_scan': 0.5, 'scan_speed': 0.5},
    'strobe slow':              {'strobe': 0.1},
    'strobe off':               {'strobe': 0.0},
    'angles':                   {'rot_x': 0.25, 'rot_y': 0.5, 'rot_z': 0.75},
    'spins':                    {'spin_x': 0.5, 'spin_y': -0.5, 'spin_z': 1.0, 'rot_z': 0.5},
    'spin stopped':             {'spin_z': 0.0, 'rot_z': 0.5},
    'move wrap':                {'move_x': 0.5, 'move_y': -0.5},
    'move gap':                 {'move_x': 1.0, 'x_move_style': 'gap'},
    'shift':                    {'x_shift_x': -0.5, 'x_shift_y': 0.5},
    'move beats shift':         {'move_x': 0.5, 'x_shift_x': -0.5},
    'zoom static':              {'zoom': 0.5},
    'zoom shrink':              {'zoom_motion': 0.5, 'zoom': 0.5},
    'zoom grow':                {'zoom_motion': 1.0, 'zoom_style': 'grow'},
    'zoom pulse':               {'zoom_motion': 0.2, 'zoom_style': 'pulse'},
    'zoom pulse 2':             {'x_zoom_pulse_2': 0.5},
    'gradient':                 {'gradient_speed': 0.5},
    'wave x':                   {'wave_x': 0.5},
    'wave y':                   {'wave_y': 0.5},
    'both waves':               {'wave_x': 0.3, 'wave_y': 0.7},
    'layer b only':             {'size@b': 0.25, 'pos_x@b': 0.5, 'spin_z@b': -1.0, 'color@b': 'green'},
    'both layers':              {'power': 'on', 'size': 0.2, 'size@b': 0.8, 'color': 'red', 'color@b': 'blue',
                                 'wave_x': 1.0, 'wave_y@b': 1.0},
    'a full look':              {'power': 'on', 'size': 0.6, 'pos_x': 0.1, 'pos_y': -0.1, 'color': 'magenta',
                                 'scan_speed': 0.9, 'strobe': 0.0, 'spin_z': 0.3, 'zoom': 1.0,
                                 'gradient_speed': 0.4},
    'another laser\'s state':   {'x_other_laser': 1, 'size@c': 0.5, 'color_effect': 'fade', 'size': 0.5},
}


def split(values: bytes) -> dict[str, list[int]]:
    return {'global': list(values[:2]), 'a': list(values[2:19]), 'b': list(values[19:])}


def render_all() -> dict[str, dict[str, list[int]]]:
    return {name: split(renderer().render(state).values) for name, state in STATES.items()}


def test_renders_match_golden():
    actual = render_all()
    if os.environ.get('PYLZR_UPDATE_GOLDEN'):
        GOLDEN.write_text(dumps(actual), encoding='utf-8', newline='\n')
        pytest.skip(f'golden file updated: {GOLDEN}')
    golden = json.loads(GOLDEN.read_text(encoding='utf-8'))
    assert list(actual) == list(golden), 'the list of states changed: regenerate the golden file'
    for name, parts in actual.items():
        values, expected = sum(parts.values(), []), sum(golden[name].values(), [])
        assert values == expected, f'{name}: ' + ', '.join(
            f'ch{ch} {g}→{v}' for ch, (g, v) in enumerate(zip(expected, values, strict=True), 1) if g != v)


def test_golden_file_is_in_canonical_form():
    assert GOLDEN.read_text(encoding='utf-8') == dumps(json.loads(GOLDEN.read_text(encoding='utf-8')))
