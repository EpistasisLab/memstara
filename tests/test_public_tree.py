"""Publication checks must reject local settings even if force-added to Git."""

import importlib.util
from pathlib import Path
import subprocess

import pytest


@pytest.fixture
def publication(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[1] / 'scripts' / 'check_public_tree.py'
    spec = importlib.util.spec_from_file_location('publication_check', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    excludes = tmp_path / '.git' / 'empty-excludes'
    excludes.write_text('')
    subprocess.run(['git', 'config', 'core.excludesFile', str(excludes)], cwd=tmp_path, check=True)
    return module, tmp_path


@pytest.mark.parametrize('name', [
    'stage-models.local.json', 'stage-models.local copy.json',
    'stage-models.local copy 2.json', 'pricing.local.backup.json',
    'azure-pricing-meters.local.json',
])
def test_local_config_cannot_be_published_without_ignore_rules(publication, name, capsys):
    module, root = publication
    (root / 'config').mkdir()
    path = root / 'config' / name
    path.write_text('{"model":"synthetic-deployment"}')
    subprocess.run(['git', 'add', '--', str(path)], cwd=root, check=True)
    assert module.main() == 1
    assert 'deployment-local configuration must not be published' in capsys.readouterr().out


def test_public_example_settings_are_allowed(publication):
    module, root = publication
    (root / 'config').mkdir()
    (root / 'config' / 'stage-models.example.json').write_text('{}')
    subprocess.run(['git', 'add', '.'], cwd=root, check=True)
    assert module.main() == 0


def test_forced_ignored_local_copy_is_rejected(publication, capsys):
    module, root = publication
    (root / '.gitignore').write_text('/config/*.local*.json\n')
    (root / 'config').mkdir()
    path = root / 'config' / 'stage-models.local copy.json'
    path.write_text('{}')
    subprocess.run(['git', 'add', '-f', '.'], cwd=root, check=True)
    assert module.main() == 1
    output = capsys.readouterr().out
    assert 'ignored file is tracked' in output
    assert 'deployment-local configuration must not be published' in output


@pytest.mark.parametrize('name', [
    '.env', '.env.production', 'deployment/.env.backup', 'server.pem', 'signing.key',
    'BACKLOG.md', 'CLAUDE.md', 'CHECKLIST_KR.md', 'daily_log/note.md',
    'anil_shared/original.md', 'phil_shared/skills/original.md',
])
def test_local_material_rejected_even_without_ignore_rules(publication, name, capsys):
    module, root = publication
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('SYNTHETIC_CONTENT_MUST_NOT_APPEAR_IN_DIAGNOSTICS')
    subprocess.run(['git', 'add', '.'], cwd=root, check=True)
    assert module.main() == 1
    output = capsys.readouterr().out
    assert 'protected local material must not be published' in output
    assert 'SYNTHETIC_CONTENT' not in output


def test_environment_template_remains_publishable(publication):
    module, root = publication
    (root / '.env.example').write_text('EXAMPLE_KEY=\n')
    subprocess.run(['git', 'add', '.'], cwd=root, check=True)
    assert module.main() == 0


def test_empty_repository_is_not_certified_as_publishable(publication, capsys):
    module, _ = publication
    assert module.main() == 1
    assert 'cannot be verified' in capsys.readouterr().out


@pytest.mark.parametrize('value', [
    'ghp_' + 'A' * 36,
    'github_pat_' + 'B' * 70,
    'AKIA' + 'C' * 16,
    '-----BEGIN ' + 'PRIVATE KEY-----',
])
def test_secret_patterns_fail_without_printing_values(publication, value, capsys):
    module, root = publication
    (root / 'settings.txt').write_text(value)
    subprocess.run(['git', 'add', '.'], cwd=root, check=True)
    assert module.main() == 1
    output = capsys.readouterr().out
    assert 'value redacted' in output
    assert value not in output
