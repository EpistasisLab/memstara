"""Deployment routing reaches new configurations and launch arguments."""
import json

import pytest

from memstara import stage_models
from memstara.control.request import build_argv
from memstara.control.workspace import PipelineWorkspace


@pytest.fixture
def profiles(tmp_path, monkeypatch):
    value = {
        "non_explanation_agents": {"provider": "openai", "model": "qwen-test"},
        "explanation_agent": {"provider": "azure_foundry", "model": "claude-sonnet-test"},
    }
    path = tmp_path / "profiles.json"
    path.write_text(json.dumps(value))
    monkeypatch.delenv("MEMSTARA_STAGE_MODELS_PATH", raising=False)
    monkeypatch.setenv("MEMSTARA_EXPLANATION_PROVIDER", "azure_foundry")
    monkeypatch.setenv("MEMSTARA_EXPLANATION_MODEL", "claude-sonnet-test")
    monkeypatch.setenv("MEMSTARA_LLM_PROVIDER", "openai")
    monkeypatch.setenv("MEMSTARA_LLM_MODEL", "qwen-test")
    return value


def test_new_workspace_and_launch_freeze_deployment_profiles(profiles):
    config = PipelineWorkspace.configuration({})
    assert config["stage_models"] == {}
    argv = build_argv({}, [])
    assert json.loads(argv[argv.index("--stage-models") + 1]) == profiles
    for stage in ("hypothesis", "hypothesis#2", "data", "ml", "interpreter", "interpreter#2"):
        assert stage_models.for_stage(profiles, stage) == profiles["non_explanation_agents"]
    assert stage_models.for_stage(profiles, "report") == profiles["explanation_agent"]


def test_saved_profiles_override_deployment_defaults(profiles):
    profiles["explanation_agent"]["model"] = "claude-sonnet-frozen"
    assert PipelineWorkspace.configuration({"stage_models": profiles})["stage_models"] == profiles
    with pytest.raises(ValueError, match="Explicitly clear"):
        build_argv({"stage_models": profiles}, [])


def test_azure_deployment_names_need_not_match_legacy_profile_keys(profiles):
    profiles['non_explanation_agents']['model'] = 'gpt-4o'
    profiles['explanation_agent']['model'] = 'clinical-explanation-deployment'
    config = PipelineWorkspace.configuration({'stage_models': profiles})
    frozen = config['stage_models']
    for stage in ('hypothesis', 'data', 'ml', 'interpreter'):
        assert stage_models.for_stage(frozen, stage)['model'] == 'gpt-4o'
    assert stage_models.for_stage(frozen, 'report')['model'] == 'clinical-explanation-deployment'


@pytest.mark.parametrize('name', ['', '   ', 42, None])
def test_invalid_deployment_names_remain_rejected(profiles, name):
    profiles['non_explanation_agents']['model'] = name
    with pytest.raises(ValueError):
        stage_models.validate_profiles(profiles)


@pytest.mark.parametrize('endpoint', [
    'https://model.example:invalid', 'https://model.example:65536',
    'https://model.example:0', 'https://model example/v1',
    ' https://model.example/v1', 'https://model.example/\napi',
    'https://model.example/\tapi', 'https://model.example/\x00api',
])
def test_malformed_endpoint_rejected_by_workspace_and_launch(profiles, endpoint):
    profiles['non_explanation_agents']['api_base'] = endpoint
    for validate in (PipelineWorkspace.configuration, lambda body: build_argv(body, [])):
        with pytest.raises(ValueError, match='Model endpoints'):
            validate({'stage_models': profiles})


@pytest.mark.parametrize('endpoint', ['https://model.example:8443/v1', 'https://[::1]:443/v1'])
def test_valid_explicit_endpoint_port_is_preserved(profiles, endpoint):
    profiles['non_explanation_agents']['api_base'] = endpoint
    assert stage_models.validate_profiles(profiles)['non_explanation_agents']['api_base'] == endpoint


def test_explicit_missing_file_never_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("MEMSTARA_STAGE_MODELS_PATH", str(tmp_path / "missing.json"))
    with pytest.raises(ValueError, match="must be migrated"):
        stage_models.deployment_profiles()


def test_invalid_profile_never_falls_back(tmp_path, monkeypatch):
    path = tmp_path / "invalid.json"
    path.write_text('{"non_explanation_agents": {"provider": "openai", "model": "qwen-test"}}')
    monkeypatch.setenv("MEMSTARA_STAGE_MODELS_PATH", str(path))
    with pytest.raises(ValueError, match="must be migrated"):
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
    wrong['explanation_agent']['model'] = 'claude-sonnet-different'
    with pytest.raises(ValueError, match='frozen execution'):
        stage_models.resolve_run_profiles(wrong, recovering=True, frozen={'stage_models': profiles})


def test_connection_summary_does_not_expose_endpoints(profiles):
    profiles['non_explanation_agents']['api_base'] = 'https://private.example.test/v1'
    assert stage_models.public_profiles(profiles)['non_explanation_agents'] == {
        'provider': 'openai', 'model': 'qwen-test'}


@pytest.mark.parametrize('stage,family', [
    ('question0-1','non_explanation_agents'), ('hypothesis0','non_explanation_agents'),
    ('hypothesis#2','non_explanation_agents'), ('data#3','non_explanation_agents'),
    ('ml#2','non_explanation_agents'), ('interpret#1','non_explanation_agents'),
    ('interpreter#2','non_explanation_agents'), ('report','explanation_agent')])
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
    with pytest.raises(ValueError, match='explanation_agent: runtime credential'):
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


@pytest.mark.parametrize('invalid', [[], False, '[]', {'non_explanation_agents': {'model': 'qwen-test'}}])
def test_web_rejects_invalid_profiles_instead_of_using_defaults(profiles, invalid):
    with pytest.raises(ValueError):
        PipelineWorkspace.configuration({'stage_models': invalid})
    with pytest.raises(ValueError):
        build_argv({'stage_models': invalid}, [])


def test_legacy_profiles_normalize_without_mutating_saved_evidence(profiles):
    import copy
    legacy = {'qwen': profiles['non_explanation_agents'], 'sonnet': profiles['explanation_agent']}
    before = copy.deepcopy(legacy)
    assert stage_models.validate_profiles(legacy) == profiles
    assert legacy == before
    assert stage_models.resolve_run_profiles(profiles, recovering=True,
                                            frozen={'stage_models': legacy}) == profiles
    for role in ('hypothesis', 'data', 'ml', 'interpreter', 'report'):
        assert stage_models.for_stage(legacy, role) == stage_models.for_stage(profiles, role)


def test_mixed_or_duplicate_profile_keys_are_rejected(profiles):
    with pytest.raises(ValueError, match='do not mix'):
        stage_models.validate_profiles({**profiles, 'qwen': profiles['non_explanation_agents']})
    with pytest.raises(ValueError, match='do not mix'):
        stage_models.validate_profiles({
            'non_explanation_agents': profiles['non_explanation_agents'],
            'sonnet': profiles['explanation_agent']})


def test_snapshot_retains_legacy_representation_only_for_same_assignment(profiles):
    legacy = {'qwen': profiles['non_explanation_agents'], 'sonnet': profiles['explanation_agent']}
    assert stage_models.snapshot_profiles(profiles, legacy) == legacy
    assert stage_models.snapshot_profiles(legacy) == profiles
    changed = {**profiles, 'non_explanation_agents': {**profiles['non_explanation_agents'], 'model': 'different'}}
    assert stage_models.snapshot_profiles(changed, legacy) == changed


def test_intermediate_role_names_preserve_routing_and_snapshot(profiles):
    old = {'analysis': profiles['non_explanation_agents'], 'explanation': profiles['explanation_agent']}
    assert stage_models.validate_profiles(old) == profiles
    assert stage_models.snapshot_profiles(profiles, old) == old
    assert stage_models.resolve_run_profiles(profiles, recovering=True, frozen={'stage_models': old}) == profiles
    with pytest.raises(ValueError, match='do not mix'):
        stage_models.validate_profiles({**profiles, 'analysis': old['analysis']})
