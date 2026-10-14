"""Fresh-user preparation validates source modes and execution skill compatibility."""
import importlib.util
import json
from pathlib import Path
import shlex

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('research_tutorial', ROOT / 'scripts/prepare_research_tutorial.py')
tutorial = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tutorial)


@pytest.mark.parametrize('knowledge', ['okf', 'llm_only'])
@pytest.mark.parametrize('data', ['dataset', 'proposal'])
def test_fresh_user_modes(tmp_path, monkeypatch, knowledge, data):
    monkeypatch.chdir(ROOT)
    monkeypatch.setenv('MEMSTARA_RESEARCH_INPUTS_DIR', str(tmp_path / 'registry'))
    monkeypatch.setenv('MEMSTARA_USER_SKILLS_DIR', str(tmp_path / 'skills'))
    monkeypatch.setenv('MEMSTARA_SPECIALIST_SKILLS_DIR', str(ROOT / 'src/memstara/resources/contributed/specialists'))
    config = json.loads((ROOT / 'examples/research-inputs/research.json').read_text())
    config.update(knowledge_mode=knowledge, data_mode=data)
    result = tutorial.prepare(config)
    assert result['execution_started'] is False
    argv = shlex.split(result['next_command'])
    assert argv[:3] == ['python', '-m', 'memstara.pipeline.board']
    assert argv[-4:] == ['--trials', '1', '--waves', '1']
    saved = json.loads((tmp_path / 'registry' / (result['research_input_id'] + '.json')).read_text())
    assert saved['input_checks_passed']
    assert saved['configuration']['data_mode'] == data
    assert saved['configuration']['knowledge_mode'] == knowledge
    for role, identifier in result['skills'].items():
        record = json.loads((tmp_path / 'skills' / (identifier + '.json')).read_text())
        assert record['stage'] == role
        assert identifier in argv
    assert not (tmp_path / 'runs').exists()


def test_invalid_input_does_not_register_skills_or_inputs(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_RESEARCH_INPUTS_DIR', str(tmp_path / 'registry'))
    monkeypatch.setenv('MEMSTARA_USER_SKILLS_DIR', str(tmp_path / 'skills'))
    with pytest.raises(ValueError):
        tutorial.prepare({'dataset_path': str(tmp_path / 'missing.csv'), 'target': {'description': 'Test'}})
    assert not (tmp_path / 'registry').exists()
    assert not (tmp_path / 'skills').exists()
