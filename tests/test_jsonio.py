"""Fixture errors and the JSON file helpers (pylzr.fixtures.errors, .jsonio)."""

import json
import os

import pytest

from pylzr.fixtures import BindingError, FixtureError
from pylzr.fixtures.errors import join_where
from pylzr.fixtures.jsonio import ObjectReader, check_type, dumps, read_file, upgrade, write_file


# ── Errors ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize('outer, inner, joined', [
    ('attributes[3]', 'range', 'attributes[3].range'),
    ('attributes', '[3]', 'attributes[3]'),
    ('', 'range', 'range'),
    ('modes', '', 'modes'),
    ('', '', ''),
])
def test_join_where(outer, inner, joined):
    assert join_where(outer, inner) == joined


def test_error_names_file_and_place():
    error = BindingError('0–300 is outside 0–255', 'attributes[3].range', 'gruolin.json')
    assert str(error) == 'gruolin.json: attributes[3].range: 0–300 is outside 0–255'
    assert str(BindingError('bad')) == 'bad'
    assert str(BindingError('bad', 'range')) == 'range: bad'
    assert isinstance(error, (FixtureError, ValueError))


def test_error_can_be_placed_later_keeping_its_type():
    error = BindingError('bad', 'range').within('attributes[3]').in_file('x.json')
    assert type(error) is BindingError
    assert (error.message, error.where, error.file) == ('bad', 'attributes[3].range', 'x.json')


# ── Types ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize('value, kind, expected', [
    (5, int, 5), (5, float, 5.0), (2.5, float, 2.5), ('a', str, 'a'), (True, bool, True),
    ([1], list, [1]), ({}, dict, {}), (None, (str, type(None)), None), (3, (int, str), 3),
])
def test_check_type_accepts(value, kind, expected):
    result = check_type(value, kind)
    assert result == expected and type(result) is type(expected)


@pytest.mark.parametrize('value, kind, message', [
    (True, int, 'must be a whole number, not true/false'),
    (False, float, 'must be a number, not true/false'),
    (2.5, int, 'must be a whole number, not the number 2.5'),
    ('5', int, 'must be a whole number, not the text "5"'),
    (None, str, 'must be text, not null'),
    ([], dict, 'must be an object, not a list'),
    (1, (str, list), 'must be text or a list, not the number 1'),
])
def test_check_type_rejects_with_a_clear_message(value, kind, message):
    with pytest.raises(BindingError, match='^range: ' + message.replace('.', r'\.')):
        check_type(value, kind, 'range', BindingError)


# ── ObjectReader ─────────────────────────────────────────────────────────

def test_reader_reads_required_and_optional_keys():
    reader = ObjectReader({'channel': 'Zoom', 'range': [0, 127]}, 'attributes[2]', BindingError)
    assert reader.required('channel', str) == 'Zoom'
    assert reader.optional('range', list) == [0, 127]
    assert reader.optional('invert', bool, False) is False
    assert reader.has('channel') and not reader.has('centre')
    reader.finish()


def test_missing_and_mistyped_keys_name_their_place():
    reader = ObjectReader({'channel': 7}, 'attributes[2]', BindingError)
    with pytest.raises(BindingError, match=r'^attributes\[2\]: "range" is missing$'):
        reader.required('range', list)
    with pytest.raises(BindingError, match=r'^attributes\[2\]\.channel: must be text, not the number 7$'):
        reader.required('channel', str)


def test_unknown_key_is_an_error_with_a_hint():
    reader = ObjectReader({'centre': 128, 'centr': 1}, 'attributes[0]', BindingError)
    reader.required('centre', int)
    with pytest.raises(BindingError, match=r'^attributes\[0\]: unknown key "centr" \(did you mean "centre"\?\)$'):
        reader.finish()


def test_unknown_key_without_a_close_match():
    reader = ObjectReader({'zzz': 1})
    reader.optional('channel', str)
    with pytest.raises(FixtureError, match='^unknown key "zzz"$'):
        reader.finish()


def test_not_an_object():
    with pytest.raises(BindingError, match=r'^layers: must be an object, not a list$'):
        ObjectReader([], 'layers', BindingError)


def test_child_and_each_carry_the_path():
    data = {'layers': {'b': 17}, 'attributes': [{'type': 'linear'}, {'type': 5}]}
    reader = ObjectReader(data, error=BindingError)
    layers = reader.child('layers')
    assert layers.where == 'layers' and layers.required('b', int) == 17
    items = list(reader.each('attributes'))
    assert [item.where for item in items] == ['attributes[0]', 'attributes[1]']
    with pytest.raises(BindingError, match=r'^attributes\[1\]\.type: must be text'):
        items[1].required('type', str)
    assert reader.child('base', required=False) is None
    assert list(reader.each('extras', required=False)) == []
    reader.finish()


def test_keys_and_rest():
    """rest() hands over the keys not asked for yet, which then count as read."""
    reader = ObjectReader({'type': 'Speed', 'speedStart': 'fast', 'speedEnd': 'slow'})
    assert reader.keys() == ['type', 'speedStart', 'speedEnd']
    reader.required('type', str)
    assert reader.rest() == {'speedStart': 'fast', 'speedEnd': 'slow'}
    assert reader.rest() == {}
    reader.finish()


def test_fail_builds_errors_at_the_right_place():
    reader = ObjectReader({'range': [0, 300]}, 'attributes[1]', BindingError)
    error = reader.fail('0–300 is outside 0–255', 'range')
    assert isinstance(error, BindingError) and error.where == 'attributes[1].range'
    assert reader.fail('bad').where == 'attributes[1]'


# ── Versions ─────────────────────────────────────────────────────────────

def test_current_version_passes_unchanged():
    data = {'version': 1, 'x': 1}
    assert upgrade(data, 1) == data


@pytest.mark.parametrize('data, message', [
    ({}, '^"version" is missing$'),
    ({'version': 0}, '^version: must be a whole number from 1, not the number 0$'),
    ({'version': '1'}, '^version: must be a whole number from 1, not the text "1"$'),
    ({'version': True}, '^version: must be a whole number from 1, not true/false$'),
    ([], '^must be an object, not a list$'),
])
def test_bad_versions(data, message):
    with pytest.raises(BindingError, match=message):
        upgrade(data, 1, error=BindingError)


def test_newer_files_are_refused_not_misread():
    with pytest.raises(FixtureError, match=r'made by a newer PyLZR \(file version 3; this version reads up to 2\)'):
        upgrade({'version': 3}, 2)


def test_older_files_are_upgraded_one_version_at_a_time():
    def add_b(d):                       # migrations may edit what they're given in place
        d['b'] = d['a'] * 2
        return d

    def add_c(d):
        d['c'] = d['b'] + 1
        return d

    migrations = {1: add_b, 2: add_c}
    original = {'version': 1, 'a': 5}
    assert upgrade(original, 3, migrations) == {'version': 3, 'a': 5, 'b': 10, 'c': 11}
    assert original == {'version': 1, 'a': 5}                     # the caller's data is untouched
    assert upgrade({'version': 2, 'a': 5, 'b': 7}, 3, migrations)['c'] == 8


def test_missing_migration_is_an_error():
    with pytest.raises(FixtureError, match='version 1 can no longer be read'):
        upgrade({'version': 1}, 2, {})


# ── Formatting ───────────────────────────────────────────────────────────

def test_dumps_is_stable_and_readable():
    data = {'version': 1, 'name': 'Gruolin → 36ch', 'range': [0, 255], 'values': {'red': {'Color': 8}},
            'list': [{'a': 1, 'b': [2]}], 'empty': {}, 'none': []}
    assert dumps(data) == (
        '{\n'
        '  "version": 1,\n'
        '  "name": "Gruolin → 36ch",\n'
        '  "range": [0, 255],\n'
        '  "values": {\n'
        '    "red": {"Color": 8}\n'
        '  },\n'
        '  "list": [\n'
        '    {\n'
        '      "a": 1,\n'
        '      "b": [2]\n'
        '    }\n'
        '  ],\n'
        '  "empty": {},\n'
        '  "none": []\n'
        '}\n'
    )
    assert json.loads(dumps(data)) == data


def test_the_whole_file_is_never_one_line():
    assert dumps({'version': 1}) == '{\n  "version": 1\n}\n'


def test_objects_in_lists_stay_expanded_so_they_line_up():
    text = dumps({'mappings': [{'type': 'linear'}], 'choices': {'line': {'type': 'linear'}}})
    assert '    {\n      "type": "linear"\n    }' in text
    assert '"line": {"type": "linear"}' in text


def test_long_lists_fill_their_lines():
    data = {'options': [f'water_{n}' for n in range(1, 50)]}
    text = dumps(data)
    lines = text.splitlines()
    assert json.loads(text) == data
    assert lines[1] == '  "options": [' and lines[-2] == '  ]'
    assert all(len(line) <= 100 for line in lines) and 4 < len(lines) < 12
    assert lines[2].startswith('    "water_1", "water_2", ')


def test_long_objects_break_over_lines():
    data = {'values': {f'channel number {i}': i for i in range(8)}}
    text = dumps(data)
    assert text.count('\n') == 12 and json.loads(text) == data      # '{', key, 8 items, '}', '}'


def test_a_value_longer_than_a_line_gets_its_own():
    data = {'notes': ['x' * 120, 'short', 'also short']}
    lines = dumps(data).splitlines()
    assert lines[2] == f'    "{"x" * 120}",' and lines[3] == '    "short", "also short"'


def test_key_order_is_kept():
    assert dumps({'b': 1, 'a': 2}).index('"b"') < dumps({'b': 1, 'a': 2}).index('"a"')


# ── Files ────────────────────────────────────────────────────────────────

def test_write_then_read(tmp_path):
    path = tmp_path / 'new' / 'folder' / 'patch.json'
    write_file(path, {'version': 1, 'name': 'Laser → L'})
    assert read_file(path) == {'version': 1, 'name': 'Laser → L'}
    assert path.read_bytes() == dumps({'version': 1, 'name': 'Laser → L'}).encode('utf-8')   # '\n', UTF-8
    assert os.listdir(path.parent) == ['patch.json']               # no temporary file left behind


def test_failed_save_keeps_the_old_file(tmp_path, monkeypatch):
    path = tmp_path / 'patch.json'
    write_file(path, {'version': 1})

    def broken_replace(src, dst):
        raise OSError('disk full')
    monkeypatch.setattr(os, 'replace', broken_replace)
    with pytest.raises(OSError):
        write_file(path, {'version': 2})
    assert read_file(path) == {'version': 1}
    assert os.listdir(tmp_path) == ['patch.json']


def test_unsaveable_data_touches_nothing(tmp_path):
    path = tmp_path / 'patch.json'
    write_file(path, {'version': 1})
    with pytest.raises(TypeError):
        write_file(path, {'version': object()})
    assert read_file(path) == {'version': 1}


def test_read_accepts_a_byte_order_mark(tmp_path):
    path = tmp_path / 'notepad.json'
    path.write_bytes(b'\xef\xbb\xbf{"version": 1}')
    assert read_file(path) == {'version': 1}


@pytest.mark.parametrize('content, message', [
    (b'{"version": 1,}', r'is not valid JSON: .* \(line 1, column \d+\)'),
    (b'\xff\xfe{}', 'is not UTF-8 text'),
])
def test_unreadable_files_name_the_file(tmp_path, content, message):
    path = tmp_path / 'broken.json'
    path.write_bytes(content)
    with pytest.raises(BindingError, match=message) as caught:
        read_file(path, BindingError)
    assert caught.value.file == str(path)


def test_missing_file(tmp_path):
    with pytest.raises(FixtureError, match='cannot be read'):
        read_file(tmp_path / 'nowhere.json')
