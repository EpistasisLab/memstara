"""Agent naming changes preserve saved definitions and historical identities."""
import json

from memstara.agent_labels import agent_label
from memstara.control.catalog import catalog
from memstara.control.workspace import PipelineWorkspace
from memstara.pipeline.prompts import load_prompt


class Manager:
    def __init__(self, key):
        self.key = key

    def running(self):
        return None

    def finished(self):
        return []


def test_old_workspace_gets_new_labels_without_changing_skills(tmp_path):
    path = tmp_path / 'workspace.json'
    old = [{'id': 'existing', 'number': 1, 'name': 'Research',
            'configuration': {'playbook_report': 'report_evidence'}}]
    path.write_text(json.dumps(old))
    workspace = PipelineWorkspace(path, Manager)
    saved = json.loads(path.read_text())[0]
    assert saved['agent_labels']['report'] == 'Explanation Agent'
    assert saved['configuration']['playbook_explanation'] == 'report_evidence'
    assert 'playbook_report' not in saved['configuration']
    assert workspace.list()[0]['id'] == 'existing'


def test_role_prompt_and_catalog_use_explanation(monkeypatch):
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: None)
    prompt = load_prompt('board/report')['system_prompt']
    assert 'final_answer' in prompt
    assert 'You are the explanation agent.' not in prompt
    assert 'You are the reporting agent.' not in prompt
    report_skills = [s for s in catalog() if s['stage'] == 'report']
    assert report_skills
    assert all(s['stage_label'] == 'Explanation Agent' for s in report_skills)
    assert agent_label('interpreter') == 'Interpreter Agent'


def test_new_workspace_uses_final_stage_defaults():
    config = PipelineWorkspace.configuration({})
    assert config['playbook_interpreter'] == 'shared-shap'
    assert config['playbook_explanation'] == 'shared-heart-failure-cardiovascular'


def test_conflicting_legacy_and_new_settings_rejected():
    import pytest
    with pytest.raises(ValueError, match='Conflicting'):
        PipelineWorkspace.configuration({'playbook_report': 'old', 'playbook_explanation': 'new'})
