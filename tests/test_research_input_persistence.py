"""A failed or concurrent registration must not expose a partial profile."""

import json
from types import SimpleNamespace

import pytest

from memstara import research_inputs as inputs
from memstara.pipeline import checkpoint


@pytest.fixture
def registry(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_RESEARCH_INPUTS_DIR', str(tmp_path))
    return tmp_path


PROFILE = {'name': 'Synthetic proposal', 'knowledge_mode': 'llm_only',
           'data_mode': 'proposal', 'target': {'description': 'Study a synthetic outcome'}}


def test_failed_serialization_leaves_previous_registration_readable(registry, monkeypatch):
    original = inputs.register(PROFILE)

    def fail(value, stream, **kwargs):
        stream.write('{"incomplete":')
        raise OSError('Simulated write failure')

    monkeypatch.setattr(json, 'dump', fail)
    with pytest.raises(OSError, match='Simulated write failure'):
        inputs.register(PROFILE)
    assert inputs.list_inputs() == [original]
    assert len(list(registry.iterdir())) == 1


def test_listing_during_serialization_sees_only_complete_profiles(registry, monkeypatch):
    original = inputs.register(PROFILE)
    dump = json.dump

    def observe(value, stream, **kwargs):
        assert inputs.list_inputs() == [original]
        return dump(value, stream, **kwargs)

    monkeypatch.setattr(json, 'dump', observe)
    second = inputs.register(PROFILE)
    assert {r['id'] for r in inputs.list_inputs()} == {original['id'], second['id']}


def test_file_sync_failure_does_not_publish_profile(registry, monkeypatch):
    def fail(fd):
        raise OSError('Simulated disk sync failure')

    monkeypatch.setattr(checkpoint.os, 'fsync', fail)
    with pytest.raises(OSError, match='Simulated disk sync failure'):
        inputs.register(PROFILE)
    assert inputs.list_inputs() == []
    assert list(registry.iterdir()) == []


def test_colliding_identifier_never_overwrites_original(registry, monkeypatch):
    original = inputs.register(PROFILE)
    before = (registry / (original['id'] + '.json')).read_bytes()
    monkeypatch.setattr(inputs.uuid, 'uuid4', lambda: SimpleNamespace(hex=original['id']))
    with pytest.raises(FileExistsError):
        inputs.register({**PROFILE, 'name': 'Different proposal'})
    assert (registry / (original['id'] + '.json')).read_bytes() == before
    assert inputs.list_inputs() == [original]
    assert len(list(registry.iterdir())) == 1
