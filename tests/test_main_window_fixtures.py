"""The fixtures list through the real main window: the library in the
fixtures folder next to the settings file, saving patch.json on every edit,
re-reading files when Settings opens, problems shown and logged, and the
'Open fixtures folder' button. Every test has its own temporary config
folder (see conftest)."""

import json
from pathlib import Path

import pytest
from shipped import GRUOLIN, resource

from pylzr.fixtures import Patch, PatchEntry, read_patch
from pylzr.fixtures.jsonio import dumps
from pylzr.gui import main_window
from pylzr.gui.settings_store import SettingsStore

GRUOLIN_NAME = 'Gruolin RGB Beam (36ch)'


def fixtures(harness):
    return harness.window.settings_panel.dmx.fixtures


def folder():
    return SettingsStore().fixtures_folder


def saved_patch():
    return read_patch(folder() / 'patch.json')


def console(harness):
    return harness.window.log_panel._text.toPlainText()


def open_settings(harness):
    """Open Settings (closing it first if it's open), as the gear does."""
    w = harness.window
    if w.settings_panel.isVisible():
        w._toggle_settings()
    w._toggle_settings()


def put(relative, data):
    path = folder() / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else dumps(data), encoding='utf-8')
    return path


def gruolin_binding(name):
    data = json.loads(resource('bindings', *f'{GRUOLIN}.json'.split('/')).read_text(encoding='utf-8'))
    return data | {'name': name}


@pytest.fixture
def answer(harness, monkeypatch):
    """Set answer['remove'] to what the 'Remove …?' question answers."""
    replies = {'remove': True}
    monkeypatch.setattr(fixtures(harness), '_confirm_remove', lambda *args: replies['remove'])
    return replies


# ── The folder and the library ───────────────────────────────────────────

def test_fixtures_folder_is_next_to_the_settings_file(harness):
    store = SettingsStore()
    assert store.fixtures_folder == Path(store.path).parent / 'fixtures'     # …/PyLZR/PyLZR.ini → …/PyLZR/fixtures
    assert store.fixtures_folder.parent.name == 'PyLZR'
    assert harness.window.library.folder == store.fixtures_folder


def test_starts_with_the_shipped_types_and_no_fixtures(harness):
    fl = fixtures(harness)
    assert (GRUOLIN, GRUOLIN_NAME) in fl.types()
    assert fl.rows() == [] and fl.file_problem_texts() == []
    assert not (folder() / 'patch.json').exists()                          # nothing written until you edit


# ── Editing saves patch.json ─────────────────────────────────────────────

def test_adding_saves_the_patch(harness):
    fl = fixtures(harness)
    fl._add_btn.click()
    fl._add_btn.click()
    expected = Patch((PatchEntry('Laser 1', GRUOLIN, 1), PatchEntry('Laser 2', GRUOLIN, 37)))
    assert saved_patch() == expected == harness.window.library.patch
    assert fl.rows() == [('Laser 1', GRUOLIN, 1), ('Laser 2', GRUOLIN, 37)]


def test_renaming_and_readdressing_save(harness):
    fl = fixtures(harness)
    fl._add_btn.click()
    fl._rows[0].name.setText('Laser L')
    fl._rows[0].name.editingFinished.emit()
    fl._rows[0].address.setValue(100)
    assert saved_patch() == Patch((PatchEntry('Laser L', GRUOLIN, 100),))


@pytest.mark.parametrize('remove', [True, False])
def test_removing_asks_first(harness, answer, remove):
    fl = fixtures(harness)
    fl._add_btn.click()
    fl._add_btn.click()
    answer['remove'] = remove
    fl._rows[0].remove.click()
    names = ('Laser 2',) if remove else ('Laser 1', 'Laser 2')
    assert saved_patch().names == names and tuple(row[0] for row in fl.rows()) == names


def test_an_overlap_is_saved_and_flagged(harness):
    fl = fixtures(harness)
    fl._add_btn.click()
    fl._add_btn.click()
    fl._rows[1].address.setValue(30)
    assert saved_patch().entries[1].address == 30
    assert fl.problem_texts() == [None, 'channels 30–65 overlap Laser 1 (1–36)']


def test_the_patch_is_restored_after_a_restart(make_window):
    first = make_window()
    fixtures(first)._add_btn.click()
    first.close()
    second = make_window()
    assert fixtures(second).rows() == [('Laser 1', GRUOLIN, 1)]


def test_reset_to_defaults_keeps_the_patch(harness):
    fixtures(harness)._add_btn.click()
    harness.window.settings_panel._reset_btn.click()
    assert saved_patch().names == ('Laser 1',)
    assert fixtures(harness).rows() == [('Laser 1', GRUOLIN, 1)]


def test_a_failed_save_is_logged_and_the_list_goes_back(harness, monkeypatch):
    fl = fixtures(harness)
    fl._add_btn.click()

    def refuse(patch):
        raise PermissionError(13, 'Permission denied')
    monkeypatch.setattr(harness.window.library, 'save_patch', refuse)
    fl._add_btn.click()
    assert fl.rows() == [('Laser 1', GRUOLIN, 1)]
    assert f"Fixtures: couldn't save {folder() / 'patch.json'} (Permission denied)" in console(harness)


# ── Files changed by hand, and problems ──────────────────────────────────

def test_a_broken_patch_never_stops_the_app(make_window):
    put('patch.json', '{"version": 1, "fixtures": [')
    harness = make_window()
    fl = fixtures(harness)
    assert fl.rows() == []
    assert len(fl.file_problem_texts()) == 1 and fl.file_problem_texts()[0].startswith('patch.json: ')
    assert console(harness).count('Fixtures: patch.json: ') == 1
    open_settings(harness)
    open_settings(harness)
    assert console(harness).count('Fixtures: patch.json: ') == 1          # logged once, however often it's shown
    fl._add_btn.click()                                                     # saving keeps the broken file aside
    assert (folder() / 'patch.unreadable.json').read_text(encoding='utf-8') == '{"version": 1, "fixtures": ['
    assert saved_patch().names == ('Laser 1',)


def test_files_added_by_hand_show_when_settings_opens(harness):
    put('bindings/mine/laser.json', gruolin_binding('My Laser'))
    assert ('mine/laser', 'My Laser') not in fixtures(harness).types()
    open_settings(harness)
    assert ('mine/laser', 'My Laser') in fixtures(harness).types()


def test_a_patch_edited_by_hand_shows_when_settings_opens(harness):
    put('patch.json', {'version': 1, 'fixtures': [{'name': 'Laser R', 'type': GRUOLIN, 'address': 37},
                                                  {'name': 'Old', 'type': 'gone/laser', 'address': 300}]})
    open_settings(harness)
    fl = fixtures(harness)
    assert fl.rows() == [('Laser R', GRUOLIN, 37), ('Old', 'gone/laser', 300)]
    assert fl.problem_texts() == [None, 'its type "gone/laser" isn\'t available']


def test_a_broken_binding_is_shown_and_logged(harness):
    put('bindings/mine/laser.json', gruolin_binding('My Laser') | {'colour': 1})
    open_settings(harness)
    [line] = fixtures(harness).file_problem_texts()
    assert line.startswith('bindings/mine/laser.json: ')
    assert f'Fixtures: {line}' in console(harness)


# ── Open fixtures folder ─────────────────────────────────────────────────

@pytest.fixture
def opened(monkeypatch):
    urls, result = [], {'ok': True}

    def open_url(url):
        urls.append(url)
        return result['ok']
    monkeypatch.setattr(main_window.QDesktopServices, 'openUrl', staticmethod(open_url))
    return urls, result


def test_open_folder_creates_and_opens_it(harness, opened):
    urls, _ = opened
    assert not folder().exists()
    fixtures(harness)._open_btn.click()
    assert folder().is_dir()
    assert [url.toLocalFile() for url in urls] == [folder().as_posix()]
    assert f'Fixtures folder: {folder()}' in console(harness)


def test_open_folder_failing_says_where_it_is(harness, opened):
    _, result = opened
    result['ok'] = False
    fixtures(harness)._open_btn.click()
    assert f"Fixtures: couldn't open {folder()}" in console(harness)
