"""A retry preserves evidence and original ordinals instead of replaying completed loops."""
import json

import pytest

from memstara.control.retry import configuration_for_retry


@pytest.fixture
def source(tmp_path):
    documents = {
        'pipeline_status.json': {'status': 'failed', 'loop': 6},
        'resume_arguments.json': {'pipeline_id': 'p', 'run_tag': 'r', 'waves': 10,
                                  'research_input_id': 'dataset'},
        'config.json': {},
        'iteration_outcomes.json': {**{str(i): {'outcome': 'completed'} for i in range(1, 6)},
                                    '6': {'outcome': 'blocked'}},
    }
    for name, value in documents.items():
        (tmp_path / name).write_text(json.dumps(value))
    return {'run_dir': str(tmp_path), 'run_tag': 'r'}, {'research_input_id': 'dataset', 'waves': 10}


def test_retry_preserves_source_and_starts_at_failed_ordinal(source):
    from pathlib import Path
    record, config = source
    before = {p.name: p.read_bytes() for p in Path(record['run_dir']).iterdir()}
    retry = configuration_for_retry(record, config, 'p')
    assert retry['_retry_from_loop'] == 6
    assert retry['waves'] == 10
    assert retry['_retry_source_run'] == 'r'
    assert config == {'research_input_id': 'dataset', 'waves': 10}
    assert before == {p.name: p.read_bytes() for p in Path(record['run_dir']).iterdir()}


@pytest.mark.parametrize('change', ['source', 'owner', 'earlier', 'missing', 'completed'])
def test_retry_rejects_unconfirmed_or_changed_source(source, change):
    from pathlib import Path
    record, config = source
    root = Path(record['run_dir'])
    owner = 'p'
    if change == 'source':
        config['research_input_id'] = 'other'
    elif change == 'owner':
        owner = 'other'
    elif change == 'earlier':
        path = root / 'iteration_outcomes.json'
        value = json.loads(path.read_text())
        value['3']['outcome'] = 'blocked'
        path.write_text(json.dumps(value))
    elif change == 'missing':
        (root / 'config.json').unlink()
    else:
        (root / 'pipeline_status.json').write_text('{"status":"completed","loop":6}')
    with pytest.raises(ValueError):
        configuration_for_retry(record, config, owner)


def test_workspace_retry_uses_latest_owned_run_and_guards_stale_click(source, tmp_path, monkeypatch):
    from pathlib import Path
    from memstara.control.workspace import PipelineWorkspace

    record, config = source

    class Manager:
        def __init__(self, key):
            self.key = key

        def running(self):
            return None

        def finished(self):
            return [record]

    workspace = PipelineWorkspace(tmp_path / 'workspace.json', Manager)
    item = workspace.mutate({'action': 'add'})
    workspace.items[0]['configuration'].update(config)
    monkeypatch.setattr(workspace, 'configuration', lambda value: dict(value))
    path = Path(record['run_dir']) / 'resume_arguments.json'
    saved = json.loads(path.read_text())
    saved['pipeline_id'] = item['id']
    path.write_text(json.dumps(saved))
    with pytest.raises(ValueError, match='history changed'):
        workspace.start(item['id'], lambda *_: pytest.fail('Must not launch'),
                        mode='retry', expected_run_tag='stale')
    result = workspace.start(item['id'], lambda manager, entry: entry['configuration'],
                             mode='retry', expected_run_tag='r')
    assert result['_retry_from_loop'] == 6
    assert result['waves'] == 10


def test_retry_restores_cli_json_settings_as_request_objects(source):
    from pathlib import Path
    record, config = source
    path = Path(record['run_dir']) / 'resume_arguments.json'
    saved = json.loads(path.read_text())
    values = {'evaluation': {}, 'ml_overrides': {}, 'controlled_comparison': {}, 'baseline_columns': []}
    config.update(values)
    saved.update({key: json.dumps(value) for key, value in values.items()})
    path.write_text(json.dumps(saved))
    retry = configuration_for_retry(record, config, 'p')
    assert {key: retry[key] for key in values} == values
