"""Skill drafts stay separate from pipelines and are saved only after user review."""
import asyncio
import json
import subprocess
from types import SimpleNamespace

import pytest

from memstara.control import skill_drafts as drafts
from memstara.control.skill_draft_worker import extract, generate


@pytest.fixture(autouse=True)
def isolated_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))


def body():
    return dict(domain='Addiction', population='Outpatient adults', features='Age and medications',
                constraints='Exclude causal claims', model='selected-deployment')


@pytest.mark.parametrize('change', [dict(stage='unknown'), dict(domain=''), dict(features='x'*4001),
                                    dict(model='https://bad?key=secret'), dict(population=None)])
def test_invalid_requests_rejected(change):
    with pytest.raises(ValueError):
        drafts.validate(body() | change)


def test_selected_model_preserved():
    assert drafts.validate(body())['model'] == 'selected-deployment'


def test_extract_envelope_and_fence():
    assert extract(json.dumps({'result':'```markdown\n# Clinical skill\n```'})) == '# Clinical skill'
    with pytest.raises(ValueError):
        extract('{"result": {}}')


def test_job_success_does_not_save_skill(monkeypatch):
    drafts._jobs['test'] = {'status':'generating', 'created':0}
    monkeypatch.setattr(subprocess, 'run', lambda *a, **k: SimpleNamespace(returncode=0,
        stdout='log\nSKILL_DRAFT:'+json.dumps({'content':'# Draft', 'model':'selected-deployment'})))
    drafts._generate('test', body())
    assert drafts.get('test') == {'status':'ready', 'content':'# Draft', 'model':'selected-deployment'}


@pytest.mark.parametrize('failure', [subprocess.TimeoutExpired('worker', 150), RuntimeError('secret-token')])
def test_failure_is_bounded_and_redacted(monkeypatch, failure):
    drafts._jobs['test'] = {'status':'generating','created':0}
    def fail(*a, **kw):
        raise failure
    monkeypatch.setattr(subprocess, 'run', fail)
    drafts._generate('test', body())
    result = drafts.get('test')
    assert result['status'] == 'failed'
    assert 'secret-token' not in result['error']


def test_job_capacity(monkeypatch):
    monkeypatch.setattr(drafts, '_jobs', {str(i):{'status':'generating','created':0} for i in range(2)})
    monkeypatch.setenv('MEMSTARA_LLM_PROVIDER', 'azure_foundry')
    monkeypatch.setenv('MEMSTARA_LLM_MODEL', 'selected-deployment')
    monkeypatch.setenv('MEMSTARA_LLM_API_BASE', 'https://example.services.ai.azure.com/anthropic')
    monkeypatch.setenv('MEMSTARA_HYPOTHESIS_MODEL', 'selected-deployment')
    with pytest.raises(ValueError, match='already'):
        drafts.start(body())


@pytest.mark.parametrize('stage', ['hypothesis','data','ml'])
def test_motoro_receives_selected_model_and_no_tools(monkeypatch, stage):
    import pytest
    pytest.importorskip("motoro", reason="Requires optional Motoro runtime; exercised in the full development suite")
    import motoro
    import motoro.runner as runner
    from memstara import env
    monkeypatch.setattr(env, 'load_env', lambda: [])
    role = {'interpreter': 'interpretation', 'report': 'explanation'}.get(stage, stage).upper()
    monkeypatch.setenv(f'MEMSTARA_{role}_PROVIDER', 'openai')
    monkeypatch.setenv(f'MEMSTARA_{role}_MODEL', 'selected-deployment')
    monkeypatch.setenv(f'MEMSTARA_{role}_API_BASE', 'https://example.org')
    monkeypatch.setattr(motoro, 'configure', lambda s: None)
    captured = {}
    async def agent(**kw):
        captured.update(kw)
        return SimpleNamespace(id='agent')
    async def run(**kw):
        captured['input'] = json.loads(kw['user_input'])
        return SimpleNamespace(id='run')
    async def execute(**kw):
        assert kw['available_tools'] == []
        return SimpleNamespace(status='completed', error=None, output='{"result":"# Reviewed later"}', total_cost=.01)
    monkeypatch.setattr(runner, 'create_agent', agent)
    monkeypatch.setattr(runner, 'create_run', run)
    monkeypatch.setattr(runner, 'execute_run', execute)
    result = asyncio.run(generate(body() | {'stage':stage}))
    assert result['stage'] == stage
    assert stage in captured['name']
    from memstara.control.skill_draft_worker import ROLE_NAMES
    assert ROLE_NAMES[stage] in captured['system_prompt']
    assert captured['model_config'].model == 'selected-deployment'
    assert captured['input']['population'] == body()['population']
    assert result['content'] == '# Reviewed later'
    assert result['run_id'] == 'run'


def test_http_routes_accept_and_poll_without_pipeline_mutation(monkeypatch):
    import pytest
    pytest.importorskip("motoro", reason="Requires optional Motoro runtime; exercised in the full development suite")
    from memstara.control.service import Handler
    handler = object.__new__(Handler)
    handler._refuse_stranger = lambda: False
    sent = []
    handler._send = lambda code, data: sent.append((code, data))
    handler._body = body
    monkeypatch.setattr(drafts, 'start', lambda data: {'id':'job','status':'generating'})
    handler.path = '/control/skill-drafts'
    handler.do_POST()
    assert sent[-1] == (202, {'id':'job','status':'generating'})
    monkeypatch.setattr(drafts, 'get', lambda key: {'status':'ready','content':'# Draft'} if key=='job' else None)
    handler.path = '/control/skill-drafts/job'
    handler.do_GET()
    assert sent[-1][1]['content'] == '# Draft'
    handler.path = '/control/skill-drafts/expired'
    handler.do_GET()
    assert sent[-1][0] == 404


@pytest.mark.parametrize('stage', ['hypothesis', 'data', 'ml'])
def test_role_survives_validation(stage):
    assert drafts.validate(body() | {'stage': stage})['stage'] == stage


def test_explanation_alias_and_role_boundaries():
    from memstara.control.skill_draft_worker import system_prompt
    for stage in ('interpreter', 'report', 'explanation'):
        with pytest.raises(ValueError, match='supplied skills'):
            drafts.validate(body() | {'stage': stage})
    assert 'Avoid speculation, causal claims, recommendations' in system_prompt('interpreter')
    assert 'further validation' in system_prompt('report')
    assert 'Do not clean, impute' in system_prompt('data')
    assert 'Preserve frozen splits' in system_prompt('ml')
