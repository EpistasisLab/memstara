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
