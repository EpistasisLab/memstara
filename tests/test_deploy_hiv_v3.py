"""Deployment sequencing without Docker, model calls or production state writes."""

import copy
import importlib.util
from pathlib import Path
import subprocess

import pytest


@pytest.fixture
def helper(tmp_path, monkeypatch):
    source = Path(__file__).resolve().parents[1] / 'deployment/deploy-hiv-v3.py'
    spec = importlib.util.spec_from_file_location('deploy_hiv_v3', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    directory = tmp_path / 'src/memstara/playbooks'
    directory.mkdir(parents=True)
    (directory / (module.V3 + '.md')).write_text('V3 instructions\n')
    return module


def menu_and_plan(helper):
    return ({'catalog': [
        {'id': helper.V3, 'content': 'V3 instructions\n', 'hash': 'new'},
        {'id': 'hiv-okf-whole-graph', 'hash': 'original'}],
        'corpus_skill_bindings': {'profiles': {'hiv': {'hypothesis': [helper.V3]}}}},
        {'plan': {'skills': {'hypothesis': [{'id': 'hiv-okf-whole-graph', 'hash': 'original'}]}},
         'first_loop': 381, 'last_loop': 1200, 'seed_schedule': {'original': True}})


@pytest.mark.parametrize('damage', [None, 'missing_v3', 'wrong_v3', 'changed_v2'])
def test_deployed_menu_requires_exact_v3_and_preserves_original_skills(helper, damage):
    menu, plan = menu_and_plan(helper)
    if damage == 'missing_v3':
        menu['corpus_skill_bindings']['profiles']['hiv']['hypothesis'] = []
    elif damage == 'wrong_v3':
        menu['catalog'][0]['content'] = 'different instructions'
    elif damage == 'changed_v2':
        menu['catalog'][1]['hash'] = 'changed'
    if damage:
        with pytest.raises(RuntimeError):
            helper.verify_catalog(menu, plan)
    else:
        helper.verify_catalog(menu, plan)


@pytest.mark.parametrize('failure', [None, 'preflight', 'build', 'changed_evidence', 'changed_seeds'])
def test_deployment_retries_only_after_all_preservation_checks(helper, monkeypatch, failure):
    events = []
    menu, plan = menu_and_plan(helper)
    record = {'run_tag': helper.SOURCE, 'run_dir': '/app/outputs/runs/original'}
    configuration = {'combination_skills': {'hypothesis': ['hiv-okf-whole-graph']}}

    class Client:
        state = 'running'

        def pipeline(self):
            running = {**record, 'execution_state': self.state} if self.state != 'ended' else None
            return {'name': 'original', 'configuration': copy.deepcopy(configuration),
                    'running': running, 'latest': record}

        def request(self, path, body=None):
            events.append((path, body))
            if path.endswith('/pause'):
                self.state = 'paused'
            elif path.endswith('/end'):
                assert self.state == 'paused'
                self.state = 'ended'
            elif path == '/control/playbooks':
                return copy.deepcopy(menu)
            elif path == '/control/runs':
                assert self.state == 'ended'
                assert body == {'pipeline_id': helper.PIPELINE, 'execution_mode': 'retry',
                                'expected_run_tag': helper.SOURCE}
                return {'run_tag': 'new-attempt'}
            return {}

    monkeypatch.setattr(helper, 'Client', Client)
    checks = []

    def preflight(*args):
        checks.append(args)
        if failure == 'preflight':
            raise RuntimeError('Not a valid interrupted loop')
        result = copy.deepcopy(plan)
        if failure == 'changed_seeds' and len(checks) == 2:
            result['seed_schedule'] = {'changed': True}
        return result

    monkeypatch.setattr(helper, 'retry_preflight', preflight)
    reads = []

    def evidence(*args):
        reads.append(args)
        return helper.ROOT, {'config': 'changed' if failure == 'changed_evidence' and len(reads) == 2
                             else 'original'}

    monkeypatch.setattr(helper, 'preserved_files', evidence)

    def run(command, **kwargs):
        events.append((command, None))
        if command == ['./start.sh'] and failure == 'build':
            raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(helper, 'run', run)
    if failure:
        with pytest.raises((RuntimeError, subprocess.CalledProcessError)):
            helper.main(True)
        assert not any(path == '/control/runs' for path, _ in events)
    else:
        helper.main(True)
        assert events[-1][0] == '/control/runs'
        assert len(checks) == 2
        assert (['./start.sh'], None) in events
    if failure == 'preflight':
        assert (['./start.sh'], None) not in events
    assert not any(isinstance(path, str) and path.endswith('/resume') for path, _ in events)
    assert all('--reset-execution-history' not in path for path, _ in events)


def test_inspection_does_not_pause_or_deploy(helper, monkeypatch):
    class Client:
        def pipeline(self):
            return {'name': 'original'}
    monkeypatch.setattr(helper, 'Client', Client)
    monkeypatch.setattr(helper, 'run', lambda *a, **k: pytest.fail('No subprocess in inspection mode'))
    helper.main(False)
