"""Check that the fakes in tests/fakes/ match the real libraries' API.

The rest of the suite runs against the fakes, so this is what catches a real
library dropping or renaming something PyLZR uses. The real packages are
inspected in a subprocess (this process has the fakes installed) and the test
is skipped where a package isn't installed.
"""

import json
import subprocess
import sys
import textwrap

import pytest

# Module attributes, and attributes of one class, that PyLZR relies on
CONTRACTS = {
    'rtmidi': (
        ['API_MACOSX_CORE', 'API_LINUX_ALSA', 'API_UNIX_JACK', 'API_WINDOWS_MM',
         'RtMidiError', 'MidiOut'],
        ('MidiOut', ['get_current_api', 'get_ports', 'open_port',
                     'open_virtual_port', 'close_port', 'send_message']),
    ),
    'pyaudio': (
        ['paInt16', 'PyAudio'],
        ('PyAudio', ['get_default_input_device_info', 'get_device_info_by_index',
                     'get_device_count', 'open', 'terminate']),
    ),
}


def missing_names(module, module_attrs, cls_name, cls_attrs):
    missing = [a for a in module_attrs if not hasattr(module, a)]
    cls = getattr(module, cls_name, None)
    missing += [f'{cls_name}.{a}' for a in cls_attrs if not hasattr(cls, a)]
    return missing


@pytest.mark.parametrize('name', sorted(CONTRACTS))
def test_real_library_has_what_pylzr_uses(name):
    module_attrs, (cls_name, cls_attrs) = CONTRACTS[name]
    code = textwrap.dedent(f'''
        import json, sys
        try:
            import {name} as m
        except ImportError:
            print(json.dumps(None)); sys.exit()
        cls = getattr(m, {cls_name!r}, None)
        missing = [a for a in {module_attrs!r} if not hasattr(m, a)]
        missing += [{cls_name!r} + '.' + a for a in {cls_attrs!r} if not hasattr(cls, a)]
        print(json.dumps(missing))
    ''')
    out = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, check=True)
    missing = json.loads(out.stdout)
    if missing is None:
        pytest.skip(f'real {name} not installed')
    assert missing == []


@pytest.mark.parametrize('name', sorted(CONTRACTS))
def test_fake_has_what_pylzr_uses(name):
    module_attrs, (cls_name, cls_attrs) = CONTRACTS[name]
    fake = sys.modules[name]
    assert missing_names(fake, module_attrs, cls_name, cls_attrs) == []
