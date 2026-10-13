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
