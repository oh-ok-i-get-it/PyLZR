"""A second, different laser for tests: the Laserworld EL-400RGB MK2 (the
vendored OFL profile in tests/data/ofl) with a small binding written here.

Where it differs from the Gruolin, which is the point of using it: one
layer, no power channel (Mode 0–49 is 'laser off', so 'no pattern' is off),
patterns chosen by Mode + Pattern Selection, its own extra
(x_dynamic_speed), and only four colours bound. Tests that run on both
lasers show the code isn't written for one of them."""

from functools import cache
from pathlib import Path

from pylzr.fixtures import compile_fixture, load_binding, read_profile

PROFILE_KEY = 'laserworld/el-400rgb-mk2'
KEY         = 'laserworld/el-400'
NAME        = 'Laserworld EL-400RGB MK2 (9ch)'
PROFILE     = Path(__file__).parent / 'data' / 'ofl' / f'{PROFILE_KEY}.json'

BINDING = {
    'version': 1, 'name': NAME, 'profile': PROFILE_KEY, 'mode': '9ch',
    'extras': [{'name': 'x_dynamic_speed', 'kind': 'continuous',
                'description': 'Speed of the dynamic patterns: 0 slow … 1 fast'}],
    'mappings': [
        {'type': 'bipolar', 'attribute': 'pos_x', 'channel': 'Horizontal Angle', 'segment': 11, 'centre': 133},
        {'type': 'bipolar', 'attribute': 'pos_y', 'channel': 'Vertical Angle', 'segment': 11, 'centre': 133},
        {'type': 'linear', 'attribute': 'scan_speed', 'channel': 'Scanning Speed'},
        {'type': 'linear', 'attribute': 'x_dynamic_speed', 'channel': 'Dynamic Pattern Speed'},
        {'type': 'linear', 'attribute': 'zoom', 'channel': 'Zoom'},
        {'type': 'options', 'attribute': 'color', 'values': {
            'white': {'Color': 2}, 'red': {'Color': 12}, 'green': {'Color': 14}, 'blue': {'Color': 10}}},
    ],
    'patterns': {'channels': ['Mode', 'Pattern Selection'], 'none': {'Mode': 0}, 'library': []},
}


def binding(data=None):
    return load_binding(data or BINDING, KEY)


@cache
def profile():
    return read_profile(PROFILE, PROFILE_KEY)


def renderer(data=None):
    return compile_fixture(binding(data), profile())
