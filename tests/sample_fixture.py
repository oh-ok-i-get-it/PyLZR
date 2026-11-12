"""A small made-up OFL profile for binding tests, with what the Gruolin
lacks: Maintenance and NoFunction segments, a gap, a segment running fast →
slow, and a second layer whose segments differ."""

import copy

from pylzr.fixtures import load_profile

KEY = 'test/sample'


def cap(start, end, kind, **properties):
    return {'dmxRange': [start, end], 'type': kind, **properties}


CHANNELS = {
    'Power': {'capabilities': [cap(0, 0, 'ShutterStrobe', shutterEffect='Closed'),
                               cap(1, 255, 'ShutterStrobe', shutterEffect='Open')]},
    'Size': {'capability': {'type': 'Zoom', 'angleStart': 'wide', 'angleEnd': 'narrow'}},
    'Position': {'defaultValue': 128,
                 'capability': {'type': 'BeamPosition', 'horizontalAngleStart': 'left', 'horizontalAngleEnd': 'right'}},
    'Spin': {'capabilities': [cap(0, 127, 'Rotation', angleStart='0deg', angleEnd='360deg'),
                              cap(128, 191, 'Rotation', speedStart='slow CW', speedEnd='fast CW'),
                              cap(192, 255, 'Rotation', speedStart='fast CCW', speedEnd='slow CCW')]},
    'Colour': {'capabilities': [cap(0, 7, 'ColorPreset', colors=['#ffffff']),
                                cap(8, 15, 'ColorPreset', colors=['#ff0000']),
                                cap(16, 255, 'Effect', effectName='Rainbow', speedStart='slow', speedEnd='fast')]},
    'Strobe': {'capabilities': [cap(0, 9, 'NoFunction'),
                                cap(10, 255, 'ShutterStrobe', shutterEffect='Strobe', speedStart='slow',
                                    speedEnd='fast')]},
    'Gap': {'capabilities': [cap(0, 99, 'Effect', effectName='Wobble', speedStart='slow', speedEnd='fast'),
                             cap(200, 255, 'Maintenance', comment='Reset')]},
    'Pattern': {'capabilities': [cap(0, 0, 'NoFunction', comment='No pattern'),
                                 cap(1, 199, 'Effect', effectName='Pattern'),
                                 cap(200, 255, 'Maintenance')]},
    'Size 2': {'capability': {'type': 'Zoom', 'angleStart': 'wide', 'angleEnd': 'narrow'}},
    'Position 2': {'defaultValue': 128,
                   'capability': {'type': 'BeamPosition', 'horizontalAngleStart': 'left',
                                  'horizontalAngleEnd': 'right'}},
    'Spin 2': {'capabilities': [cap(0, 255, 'Rotation', speedStart='slow CW', speedEnd='fast CW')]},  # differs
    'Colour 2': {'capabilities': [cap(0, 7, 'ColorPreset', colors=['#ffffff']),
                                  cap(8, 15, 'ColorPreset', colors=['#ff0000']),
                                  cap(16, 255, 'Effect', effectName='Rainbow', speedStart='slow',
                                      speedEnd='fast')]},
    'Strobe 2': {'capabilities': [cap(0, 9, 'NoFunction'),
                                  cap(10, 255, 'ShutterStrobe', shutterEffect='Strobe', speedStart='slow',
                                      speedEnd='fast')]},
    'Gap 2': {'capabilities': [cap(0, 99, 'Effect', effectName='Wobble', speedStart='slow', speedEnd='fast'),
                               cap(200, 255, 'Maintenance', comment='Reset')]},
    'Pattern 2': {'capabilities': [cap(0, 0, 'NoFunction', comment='No pattern'),
                                   cap(1, 99, 'Effect', effectName='Pattern'),
                                   cap(100, 255, 'Maintenance')]},              # fewer patterns on layer b
}

# Layer a is channels 2–8, layer b 7 channels on (9–15)
LAYER = ['Size', 'Position', 'Spin', 'Colour', 'Strobe', 'Gap', 'Pattern']
MODE = ['Power', *LAYER, *[f'{name} 2' for name in LAYER]]

PROFILE = {
    'name': 'Sample Laser',
    'categories': ['Laser'],
    'availableChannels': CHANNELS,
    'modes': [{'name': 'Full', 'shortName': '15ch', 'channels': MODE},
              {'name': 'Short', 'shortName': '3ch', 'channels': ['Power', 'Size', None]}],
}


def profile(key: str = KEY):
    return load_profile(copy.deepcopy(PROFILE), key)
