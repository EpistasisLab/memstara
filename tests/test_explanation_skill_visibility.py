"""Disabled Explanation choices are readable history, not executable experiments."""
import asyncio
import json
from types import SimpleNamespace

import pytest
from memstara.control import catalog
from memstara.pipeline import prompts


@pytest.fixture
def shared(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, 'anil_dir', lambda: tmp_path)
    monkeypatch.setenv('MEMSTARA_USER_SKILLS_DIR', str(tmp_path / 'users'))
    for filename in ('Addiction-Expert-Explanation.md', 'HIV-Expert-Explanation.md'):
        (tmp_path / filename).write_text('# Synthetic shared expert\nExplain measured results.')
    presenter = tmp_path / 'presenter.md'
    presenter.write_text('# Synthetic presenter\nReport metrics.')
    monkeypatch.setenv('MEMSTARA_RESULTS_SKILL_PATH', str(presenter))
    monkeypatch.delenv('MEMSTARA_RUN_CONFIG', raising=False)


def test_current_domain_explanations_and_general_choice_visible(shared):
    assert {i['id'] for i in catalog.catalog() if i['stage'] == 'report'} == {
        'shared-anil-addiction', 'shared-anil-hiv', 'report_general',
        'report_heart_failure_cardiovascular', 'report_heart_failure_cardiorenal'}
    for name in ('shared-anil-addiction', 'shared-anil-hiv'):
        catalog.validate_selection({'playbook_explanation': name})


@pytest.mark.parametrize('name', sorted(prompts.DISABLED_EXPLANATION_SKILLS))
def test_disabled_skills_remain_readable_but_cannot_launch(shared, name):
    assert catalog.resolve(name)['stage'] == 'report'
    assert prompts.load_prompt('board/report', name)['system_prompt']
    with pytest.raises(ValueError, match='disabled for execution'):
        catalog.validate_selection({'playbook_explanation': name})


@pytest.mark.parametrize('combination', [False, True])
@pytest.mark.parametrize('mode', ['dataset', 'proposal'])
def test_board_rejects_disabled_skill_before_execution(tmp_path, combination, mode):
    from memstara.pipeline.board import run
    args = SimpleNamespace(data_mode=mode, playbook_explanation='' if combination else 'report_evidence',
                           combination_plan=json.dumps({'skills': {'report': [{'id': 'report_evidence'}]}})
                           if combination else '')
    with pytest.raises(ValueError, match='disabled for execution'):
        asyncio.run(run(args, tmp_path))
    assert list(tmp_path.iterdir()) == []
