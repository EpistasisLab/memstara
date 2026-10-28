"""Checked GUI models become durable defaults without changing saved experiments."""
import json

import pytest

from memstara import model_connections as connections, model_defaults


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    monkeypatch.delenv('MOTORO_ENCRYPTION_KEY', raising=False)
    monkeypatch.setattr(connections, 'probe', lambda data: None)
    monkeypatch.setattr(model_defaults, 'public_defaults', lambda: {
        'source': 'project_env', 'profiles': [], 'restart_required_after_edit': True})
    return tmp_path / 'private-model-connections'


def save(model='my-deployment'):
    return connections.check_and_save({
        'provider': 'azure_foundry', 'model': model,
        'api_base': 'https://fixture.services.ai.azure.com', 'api_key': 'synthetic-private-key',
        'settings': {'max_tokens': 6000},
    }, make_default=True)


def test_checked_default_survives_reload_and_reaches_all_agents(store, monkeypatch):
    assert model_defaults.experiment_defaults()['setup_required']
    saved = save()
    # Loading uses persisted files, not a process-global remembered object or a new paid probe.
    monkeypatch.setattr(connections, 'probe', lambda _: pytest.fail('No repeat model call'))
    from test_control_model_policy import handler
    request = handler('/control/model-defaults', {})
    request.do_GET()
    status, body = request._send.call_args.args
    assert status == 200 and body['current_allowed'] and not body['setup_required']
    assert body['connection'] == saved and body['source'] == 'saved_connection'
    assert 'synthetic-private-key' not in json.dumps(body)
    assert json.loads((store / 'default.json').read_text()) == {'connection_id': saved['id']}
    env = connections.execution_environment(body['connection']['id'], {})
    from memstara.operational import model_profiles
    profiles = model_profiles(env)
    assert len(profiles) == 6
    assert all(p['model'] == 'my-deployment' and p['max_tokens'] == 6000 for p in profiles.values())


def test_new_default_does_not_rewrite_earlier_experiment_connection(store):
    first = save()
    frozen = (store / (first['id'] + '.enc')).read_bytes()
    second = save('next-deployment')
    assert connections.current_default() == second
    assert (store / (first['id'] + '.enc')).read_bytes() == frozen
    assert connections.execution_environment(first['id'], {})['MEMSTARA_LLM_MODEL'] == 'my-deployment'


def test_failed_check_keeps_previous_default(store, monkeypatch):
    previous = save()
    def fail(_):
        raise ValueError('Authentication failed')
    monkeypatch.setattr(connections, 'probe', fail)
    with pytest.raises(ValueError, match='Authentication failed'):
        save('invalid-deployment')
    assert connections.current_default() == previous
    assert len(list(store.glob('*.enc'))) == 1


@pytest.mark.parametrize('damage', ['missing_record', 'corrupt_record', 'corrupt_pointer'])
def test_unavailable_saved_default_never_silently_selects_environment(store, monkeypatch, damage):
    saved = save()
    record = store / (saved['id'] + '.enc')
    if damage == 'missing_record':
        record.unlink()
    elif damage == 'corrupt_record':
        record.write_text('synthetic-private-diagnostic')
    else:
        (store / 'default.json').write_text('synthetic-private-diagnostic')
    monkeypatch.setattr(model_defaults, 'public_defaults', lambda: {
        'source': 'project_env', 'profiles': [{'provider': 'azure_foundry', 'credentials_available': True}]})
    body = model_defaults.experiment_defaults()
    assert not body['current_allowed'] and body['setup_required']
    assert 'connection' not in body and 'unavailable' in body['current_error']
    assert 'synthetic-private' not in json.dumps(body)


def test_without_saved_default_environment_profiles_remain_available(store, monkeypatch):
    profiles = [{'provider': 'azure_foundry', 'model': 'server-model', 'credentials_available': True}]
    monkeypatch.setattr(model_defaults, 'public_defaults', lambda: {'profiles': profiles})
    body = model_defaults.experiment_defaults()
    assert body['current_allowed'] and body['profiles'] == profiles and 'connection' not in body


def test_native_connection_does_not_replace_gui_default(store):
    previous = save()
    connections.check_and_save({'provider': 'openai', 'model': 'native-model', 'api_key': 'synthetic'})
    assert connections.current_default() == previous
