"""Explicit recovery policy preserves original configuration and split identity."""
import json
import pytest
from memstara.evaluation import active_plan
from memstara.ml_configuration import policy


def test_override_is_scoped_and_leaves_saved_configuration_unchanged(tmp_path, monkeypatch):
    original = {'run_tag': 'saved-run', 'config_hash': 'frozen',
                'evaluation': {'seed': 7, 'replicates': 3},
                'ml_configuration_policy': {**policy(), 'max_fits': 120, 'wall_seconds': 600}}
    source = tmp_path / 'config.json'
    source.write_text(json.dumps(original))
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', str(source))
    assert active_plan()['ml_configuration_policy']['max_fits'] == 120
    override = {'version': 1, 'run_tag': 'saved-run', 'config_hash': 'frozen',
                'limits': {k: v for k, v in policy().items() if v is None}}
    file = tmp_path / 'ml_resource_override.json'
    file.write_text(json.dumps(override))
    effective = active_plan()
    assert effective['ml_configuration_policy']['max_fits'] is None
    assert effective['config_hash'] == 'frozen'
    assert effective['evaluation'] == original['evaluation']
    assert json.loads(source.read_text()) == original
    override['run_tag'] = 'another-run'
    file.write_text(json.dumps(override))
    with pytest.raises(ValueError, match='does not match'):
        active_plan()


def test_override_cannot_change_statistical_settings(tmp_path, monkeypatch):
    source = tmp_path / 'config.json'
    source.write_text(json.dumps({'run_tag': 'r', 'config_hash': 'c'}))
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', str(source))
    (tmp_path / 'ml_resource_override.json').write_text(json.dumps(
        {'version': 1, 'run_tag': 'r', 'config_hash': 'c', 'limits': {'seed': None}}))
    with pytest.raises(ValueError, match='Invalid explicit'):
        active_plan()
