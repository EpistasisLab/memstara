"""Deployment routing reaches new configurations and launch arguments."""
import json

import pytest

from memstara import stage_models
from memstara.control.request import build_argv
from memstara.control.workspace import PipelineWorkspace


@pytest.fixture
def profiles(tmp_path, monkeypatch):
    value = {
        "qwen": {"provider": "openai", "model": "qwen-test"},
        "sonnet": {"provider": "azure_foundry", "model": "claude-sonnet-test"},
    }
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(value))
    monkeypatch.setenv("MEMSTARA_STAGE_MODELS_PATH", str(path))
    monkeypatch.setenv("MEMSTARA_LLM_PROVIDER", "openai")
    monkeypatch.setenv("MEMSTARA_LLM_MODEL", "qwen-test")
    return value


def test_new_workspace_and_launch_freeze_deployment_profiles(profiles):
    config = PipelineWorkspace.configuration({})
    assert config["stage_models"] == profiles
    argv = build_argv({}, [])
    assert json.loads(argv[argv.index("--stage-models") + 1]) == profiles
    for stage in ("hypothesis", "hypothesis#2", "data", "ml", "interpreter", "interpreter#2"):
        assert stage_models.for_stage(config["stage_models"], stage) == profiles["qwen"]
    assert stage_models.for_stage(config["stage_models"], "report") == profiles["sonnet"]


def test_saved_profiles_override_deployment_defaults(profiles):
    profiles["sonnet"]["model"] = "claude-sonnet-frozen"
    assert PipelineWorkspace.configuration({"stage_models": profiles})["stage_models"] == profiles
    argv = build_argv({"stage_models": profiles}, [])
    assert json.loads(argv[argv.index("--stage-models") + 1]) == profiles


def test_explicit_missing_file_never_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMSTARA_STAGE_MODELS_PATH", str(tmp_path / "missing.json"))
    with pytest.raises(ValueError, match="missing or invalid"):
        stage_models.deployment_profiles()


def test_invalid_profile_never_falls_back(tmp_path, monkeypatch):
    path = tmp_path / "invalid.json"
    path.write_text('{"qwen": {"provider": "openai", "model": "qwen-test"}}')
    monkeypatch.setenv("MEMSTARA_STAGE_MODELS_PATH", str(path))
    with pytest.raises(ValueError, match="missing or invalid"):
        stage_models.deployment_profiles()


@pytest.mark.parametrize('recovery', [True, False])
def test_invalid_nonobject_profiles_are_rejected(recovery):
    with pytest.raises(ValueError):
        stage_models.resolve_run_profiles([], recovering=recovery)


def test_recovery_uses_only_frozen_profiles(profiles, monkeypatch):
    monkeypatch.setattr(stage_models, 'deployment_profiles', lambda: pytest.fail('No recovery defaults'))
    assert stage_models.resolve_run_profiles({}, recovering=True, frozen={'stage_models': profiles}) == profiles
    assert stage_models.resolve_run_profiles({}, recovering=True, frozen={}) == {}
    wrong = json.loads(json.dumps(profiles))
    wrong['sonnet']['model'] = 'claude-sonnet-different'
    with pytest.raises(ValueError, match='frozen execution'):
        stage_models.resolve_run_profiles(wrong, recovering=True, frozen={'stage_models': profiles})


def test_connection_summary_does_not_expose_endpoints(profiles):
    profiles['qwen']['api_base'] = 'https://private.example.test/v1'
    assert stage_models.public_profiles(profiles)['qwen'] == {'provider': 'openai', 'model': 'qwen-test'}


@pytest.mark.parametrize('stage,family', [('question0-1','qwen'), ('hypothesis0','qwen'),
    ('hypothesis#2','qwen'), ('data#3','qwen'), ('ml#2','qwen'), ('interpret#1','qwen'),
    ('interpreter#2','qwen'), ('report','sonnet')])
def test_every_runtime_stage_refuses_a_wrong_model(profiles, stage, family):
    from types import SimpleNamespace
    config = SimpleNamespace(**profiles[family])
    stage_models.validate_call(config, stage, {'stage_models': profiles})
    config.model = 'wrong-deployment'
    with pytest.raises(ValueError, match='frozen stage assignment'):
        stage_models.validate_call(config, stage, {'stage_models': profiles})


def test_every_combination_retains_profiles_for_both_experts(profiles):
    import asyncio
    from unittest.mock import AsyncMock
    from memstara.combinations import prepare_loop
    stages = ('hypothesis', 'data', 'ml', 'interpreter', 'report')
    plan = {'version': 1, 'combinations': 4, 'total_loops': 8,
            'skills': {s: [{'id': name}] for s, name in zip(stages,
                ['random_features','data','ml','shap','addiction'], strict=True)}}
    plan['skills']['interpreter'] = [{'id': 'shap'}, {'id': 'lime'}]
    plan['skills']['report'] = [{'id': 'addiction'}, {'id': 'hiv'}]
    provision = AsyncMock(return_value={s:s for s in stages})
    for loop in range(1, 9):
        asyncio.run(prepare_loop(plan, loop, provider='openai', model='ignored', run_tag='fixture',
                                 provision=provision, stage_models=profiles))
    assert provision.await_count == 8
    assert all(c.kwargs['stage_models'] == profiles for c in provision.await_args_list)
    assert {c.kwargs['playbooks']['report'][0] for c in provision.await_args_list} == {'addiction', 'hiv'}


def test_missing_sonnet_credential_blocks_before_inference(profiles, monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock
    pytest.importorskip('motoro')
    resolver = AsyncMock(side_effect=[{'api_key': 'synthetic'}, {}])
    monkeypatch.setattr('motoro.services.credentials.resolve', resolver)
    with pytest.raises(ValueError, match='sonnet: runtime credential'):
        asyncio.run(stage_models.preflight_profiles(profiles))
    assert resolver.await_count == 2


def test_resolver_cannot_silently_replace_model(profiles, monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock
    pytest.importorskip('motoro')
    monkeypatch.setattr('motoro.services.credentials.resolve', AsyncMock(
        return_value={'api_key': 'synthetic', 'model': 'different-model'}))
    with pytest.raises(ValueError, match='resolver changed'):
        asyncio.run(stage_models.preflight_profiles(profiles))


@pytest.mark.parametrize('invalid', [[], False, '[]', {'qwen': {'model': 'qwen-test'}}])
def test_web_rejects_invalid_profiles_instead_of_using_defaults(profiles, invalid):
    with pytest.raises(ValueError):
        PipelineWorkspace.configuration({'stage_models': invalid})
    with pytest.raises(ValueError):
        build_argv({'stage_models': invalid}, [])
