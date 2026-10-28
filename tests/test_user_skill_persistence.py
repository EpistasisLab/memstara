"""User skill versions are immutable; failed publication retains existing evidence."""
import json

import pytest

from memstara.control import catalog


@pytest.fixture
def skill_store(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_USER_SKILLS_DIR', str(tmp_path))
    return tmp_path


def test_repeated_skill_registration_keeps_existing_file(skill_store):
    body = {'stage': 'data', 'name': 'example', 'content': '# Synthetic instructions'}
    first = catalog.register(body)
    path = skill_store / (first['id'] + '.json')
    inode = path.stat().st_ino
    assert catalog.register(body) == first
    assert path.stat().st_ino == inode


def test_colliding_skill_identifier_never_overwrites_existing_version(skill_store, monkeypatch):
    original = catalog._entry

    def collision(*args):
        return {**original(*args), 'hash': 'a' * 64}

    monkeypatch.setattr(catalog, '_entry', collision)
    first = catalog.register({'stage': 'data', 'name': 'example', 'content': '# First'})
    path = skill_store / (first['id'] + '.json')
    saved = path.read_bytes()
    with pytest.raises(ValueError, match='different content'):
        catalog.register({'stage': 'data', 'name': 'example', 'content': '# Second'})
    assert path.read_bytes() == saved
    assert list(skill_store.iterdir()) == [path]


def test_failed_skill_flush_publishes_no_record_or_temporary_file(skill_store, monkeypatch):
    from memstara.pipeline import checkpoint

    def fail(_):
        raise OSError('Synthetic disk failure')

    monkeypatch.setattr(checkpoint.os, 'fsync', fail)
    with pytest.raises(OSError, match='Synthetic disk failure'):
        catalog.register({'stage': 'data', 'name': 'example', 'content': '# Synthetic'})
    assert list(skill_store.iterdir()) == []


def test_changed_skill_creates_a_separate_version(skill_store):
    first = catalog.register({'stage': 'data', 'name': 'example', 'content': '# First'})
    second = catalog.register({'stage': 'data', 'name': 'example', 'content': '# Second'})
    assert first['id'] != second['id']
    assert json.loads((skill_store / (first['id'] + '.json')).read_text()) == first
    assert json.loads((skill_store / (second['id'] + '.json')).read_text()) == second


@pytest.mark.parametrize('conflicting', [False, True])
def test_concurrent_registrations_preserve_one_complete_version(skill_store, monkeypatch, conflicting):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    original = catalog._entry
    barrier = Barrier(2)

    def entry(*args):
        item = original(*args)
        barrier.wait(timeout=5)
        return {**item, 'hash': 'b' * 64}

    monkeypatch.setattr(catalog, '_entry', entry)
    bodies = [{'stage': 'data', 'name': 'example', 'content': '# First'},
              {'stage': 'data', 'name': 'example', 'content': '# Second' if conflicting else '# First'}]
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(catalog.register, body) for body in bodies]
    successes = [f.result() for f in futures if f.exception() is None]
    errors = [f.exception() for f in futures if f.exception() is not None]
    assert len(successes) == (1 if conflicting else 2)
    assert len(errors) == (1 if conflicting else 0)
    assert all(isinstance(error, ValueError) for error in errors)
    files = list(skill_store.iterdir())
    assert len(files) == 1
    assert json.loads(files[0].read_text()) == successes[0]


def named(name='request-one', title='심부전 Risk factors', content='# AI heading'):
    return {'stage': 'hypothesis', 'name': name, 'display_name': title, 'content': content}


def test_user_name_is_library_title_without_rewriting_markdown(skill_store):
    first = catalog.register(named())
    assert first['title'] == '심부전 Risk factors'
    assert first['content'] == '# AI heading'
    assert catalog.resolve(first['id'])['title'] == first['title']
    assert catalog.register(named()) == first  # Lost HTTP response: retry is idempotent.
    second = catalog.register(named('request-two'))
    third = catalog.register(named('request-three'))
    assert [second['title'], third['title']] == ['심부전 Risk factors (2)', '심부전 Risk factors (3)']
    assert first['hash'] == second['hash']  # Display names do not change scientific identity.
    assert json.loads((skill_store / (first['id'] + '.json')).read_text()) == first


def test_names_are_case_insensitive_role_scoped_and_uncached(skill_store):
    first = catalog.register(named(title='Study'))
    with catalog.catalog_snapshot():
        catalog.catalog()
        second = catalog.register(named('two', 'study'))
        third = catalog.register(named('three', 'Study'))
    assert second['title'] == 'study (2)' and third['title'] == 'Study (3)'
    other = catalog.register(named('data', 'Study') | {'stage': 'data', 'base_skill': 'data_training_heavy'})
    assert other['title'] == first['title']


def test_long_duplicate_names_remain_bounded(skill_store):
    catalog.register(named(title='가' * 80))
    duplicate = catalog.register(named('two', '가' * 80))
    assert len(duplicate['title']) == 80 and duplicate['title'].endswith(' (2)')


@pytest.mark.parametrize('title', ['', '   ', 'a' * 81, 'bad\nname', '\0name', [], 12])
def test_invalid_display_names_never_write(skill_store, title):
    with pytest.raises(ValueError, match='skill name'):
        catalog.register(named(title=title))
    assert list(skill_store.iterdir()) == []


@pytest.mark.parametrize('identical', [False, True])
def test_concurrent_display_name_reservations_are_unique_and_retry_safe(skill_store, identical):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier = Barrier(4)
    def save(index):
        barrier.wait(timeout=5)
        return catalog.register(named('same' if identical else f'request-{index}', 'Research skill'))
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(save, range(4)))
    assert len({row['id'] for row in results}) == (1 if identical else 4)
    assert {row['title'] for row in results} == ({'Research skill'} if identical else {
        'Research skill', 'Research skill (2)', 'Research skill (3)', 'Research skill (4)'})
    assert len(list(skill_store.glob('*.json'))) == (1 if identical else 4)
