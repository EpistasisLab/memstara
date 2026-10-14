"""Malformed saved skill records yield actionable, redacted catalog errors."""
import json

import pytest

from memstara.control import catalog


@pytest.mark.parametrize('text', ['{', '[]', 'null', '{}', '{"stage":"unknown"}'])
def test_invalid_saved_skill_is_rejected_without_rewriting(tmp_path, monkeypatch, text):
    monkeypatch.setattr(catalog, 'anil_skills', lambda: [])
    monkeypatch.setattr(catalog, 'document_path', lambda *args: None)
    monkeypatch.setattr(catalog, 'user_dir', lambda: tmp_path)
    path = tmp_path / 'broken.json'
    path.write_text(text)
    with pytest.raises(ValueError, match='saved user skill'):
        catalog.catalog()
    assert path.read_text() == text


@pytest.mark.parametrize('value', [[], None, 5, {'legacy': []}, {'legacy': ''}])
def test_invalid_alias_map_is_rejected(tmp_path, monkeypatch, value):
    path = tmp_path / 'aliases.json'
    path.write_text(json.dumps(value))
    monkeypatch.setenv('MEMSTARA_SKILL_ALIASES_PATH', str(path))
    with pytest.raises(ValueError, match='Skill aliases'):
        catalog.canonical_name('legacy')


@pytest.mark.parametrize('error', [ValueError('private-content'), OSError('private-path')])
def test_catalog_http_failure_is_structured_and_redacted(monkeypatch, error):
    from memstara.control import service
    handler = object.__new__(service.Handler)
    handler.path = '/control/playbooks'
    handler._refuse_stranger = lambda: False
    sent = []
    handler._send = lambda code, payload: sent.append((code, payload))

    def fail():
        raise error

    monkeypatch.setattr(service, 'playbooks', fail)
    handler.do_GET()
    assert sent[0][0] == 503
    assert 'Skill catalog' in sent[0][1]['error']
    assert 'private-' not in json.dumps(sent)


def test_playbook_ids_and_records_use_one_snapshot(monkeypatch):
    from memstara.control import service
    calls = []

    def read():
        calls.append(1)
        return [{'id': str(len(calls))}]

    monkeypatch.setattr(service, 'catalog', read)
    monkeypatch.setattr(service, 'reference_knowledge', lambda: [])
    result = service.playbooks()
    assert result['playbooks'] == [item['id'] for item in result['catalog']]
    assert len(calls) == 1


@pytest.mark.parametrize('error', [ValueError('private-content'), OSError('private-path')])
def test_invalid_catalog_blocks_launch_before_any_run_creation(monkeypatch, error):
    from unittest.mock import Mock
    from memstara.control import service
    handler = object.__new__(service.Handler)
    sent = []
    handler._send = lambda code, payload: sent.append((code, payload))
    manager = Mock()

    def fail():
        raise error

    monkeypatch.setattr(service, 'playbooks', fail)
    create = Mock(side_effect=AssertionError('Must not create a run'))
    monkeypatch.setattr(service, 'new_run_dir', create)
    handler._launch({'knowledge_mode': 'llm_only', 'data_mode': 'proposal'}, manager)
    assert sent[0][0] == 503
    assert 'Run not started' in sent[0][1]['error']
    assert 'private-' not in json.dumps(sent)
    create.assert_not_called()
    manager.start.assert_not_called()
