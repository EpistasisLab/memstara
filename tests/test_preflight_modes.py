"""Environment diagnostics follow selected inputs without starting services."""

from itertools import product
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from memstara import env, preflight


@pytest.fixture(autouse=True)
def clean_checks(monkeypatch):
    preflight._failures.clear()
    for name in env.BASE_VARS:
        monkeypatch.delenv(name, raising=False)
    yield
    preflight._failures.clear()


@pytest.mark.parametrize('knowledge,data', tuple(product(('okf', 'llm_only'), ('dataset', 'proposal'))))
def test_required_sources_depend_on_modes(monkeypatch, knowledge, data):
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', 'synthetic-output')
    monkeypatch.setenv('MOTORO_DATABASE_URL', 'synthetic-database')
    problems = env.missing_vars(knowledge_mode=knowledge, data_mode=data)
    assert any(p.startswith('AGENTIC_OKF_BUNDLE_DIR ') for p in problems) == (knowledge == 'okf')
    assert any(p.startswith('MEMSTARA_DATASET_PATH ') for p in problems) == (data == 'dataset')
    assert len(problems) == int(knowledge == 'okf') + int(data == 'dataset')


def test_missing_env_files_do_not_reject_process_configuration(monkeypatch, tmp_path):
    monkeypatch.setattr(preflight, 'ENV_FILES', (tmp_path / 'absent.env',))
    preflight.check_env_files()
    assert preflight._failures == []


def test_no_input_mode_does_not_access_unused_paths(monkeypatch, tmp_path):
    monkeypatch.setenv('AGENTIC_OKF_BUNDLE_DIR', '/unused/knowledge')
    monkeypatch.setenv('MEMSTARA_DATASET_PATH', '/unused/dataset.csv')
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    directory = preflight.Path.is_dir

    def selected_only(path):
        assert str(path) == str(tmp_path)
        return directory(path)

    monkeypatch.setattr(preflight.Path, 'is_dir', selected_only)
    monkeypatch.setattr(preflight.Path, 'is_file', lambda path: pytest.fail('No dataset file access'))
    preflight.check_paths(knowledge_mode='llm_only', data_mode='proposal')
    assert not preflight._failures


def test_selected_dataset_still_rejects_missing_file(monkeypatch, tmp_path):
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    preflight.check_paths(knowledge_mode='llm_only', data_mode='dataset')
    assert preflight._failures == ['data csv']


@pytest.mark.parametrize('data,expected', [('dataset', 4), ('proposal', 0)])
def test_unselected_server_imports_are_not_started(monkeypatch, data, expected):
    start = Mock(return_value=SimpleNamespace(returncode=0))
    monkeypatch.setattr(preflight.subprocess, 'run', start)
    preflight.check_servers(knowledge_mode='llm_only', data_mode=data)
    assert start.call_count == expected
    assert all('memstara.mcp_servers.okf' not in c.args[0][2] for c in start.call_args_list)


def test_cli_proposal_skips_matcher_and_resets_prior_diagnostic_failures(monkeypatch):
    preflight._failures.append('prior invocation')
    monkeypatch.setattr(preflight.sys, 'argv', ['preflight', '--quick', '--knowledge-mode', 'llm_only',
                                              '--data-mode', 'proposal'])
    monkeypatch.setattr(preflight, 'check_env_files', lambda: None)
    variables, paths = Mock(), Mock()
    monkeypatch.setattr(preflight, 'check_vars', variables)
    monkeypatch.setattr(preflight, 'check_paths', paths)

    async def no_database_access():
        pass

    monkeypatch.setattr(preflight, 'check_databases', no_database_access)
    monkeypatch.setattr(preflight, 'check_allowlist', lambda: None)
    monkeypatch.setattr(preflight, 'check_matcher_catalog', lambda: pytest.fail('No matcher in proposal mode'))
    monkeypatch.setattr(preflight, 'check_servers', lambda **kwargs: pytest.fail('Quick skips subprocesses'))
    assert preflight.main() == 0
    modes = {'knowledge_mode': 'llm_only', 'data_mode': 'proposal'}
    variables.assert_called_once_with('azure_foundry', **modes)
    paths.assert_called_once_with(**modes)


def test_omitting_inputs_does_not_omit_provider_credentials(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    problems = env.missing_vars('openai', knowledge_mode='llm_only', data_mode='proposal')
    assert any(p.startswith('OPENAI_API_KEY ') for p in problems)
