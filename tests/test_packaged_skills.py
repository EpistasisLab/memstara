"""A fresh installation resolves current contributed bytes without sibling files."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from memstara.control import catalog
from memstara.paths import PACKAGE_ROOT

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def standalone(monkeypatch, tmp_path):
    for key in ('MEMSTARA_SPECIALIST_SKILLS_DIR', 'MEMSTARA_SHARED_SKILLS_DIR',
                'MEMSTARA_RESULTS_SKILL_PATH', 'MEMSTARA_ML_REFERENCE_PATH'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('MEMSTARA_USER_SKILLS_DIR', str(tmp_path / 'users'))
    return tmp_path


def test_standalone_catalog_and_preserved_hashes(standalone):
    rows = catalog.catalog()
    assert [sum(r['stage'] == stage for r in rows) for stage in catalog.ROLES] == [8, 2, 2, 2, 5]
    bundle = PACKAGE_ROOT / 'resources/contributed'
    manifest = json.loads((bundle / 'manifest.json').read_text())
    for entry in manifest['files']:
        assert hashlib.sha256((bundle / entry['path']).read_bytes()).hexdigest() == entry['sha256']
    assert len(catalog.reference_knowledge()) == 1
    assert catalog.resolve('shared-ml-results')['stage'] == 'report'
    assert all(r['id'] != 'shared-ml-results' for r in rows)


def test_explicit_missing_directory_does_not_fall_back(standalone, monkeypatch):
    monkeypatch.setenv('MEMSTARA_SPECIALIST_SKILLS_DIR', str(standalone / 'missing'))
    with pytest.raises(FileNotFoundError):
        catalog.resolve('shared-anil-shap')
    monkeypatch.setenv('MEMSTARA_SHARED_SKILLS_DIR', str(standalone / 'missing'))
    assert catalog.reference_knowledge() == []


def test_default_is_internal_even_when_sibling_exists(standalone, monkeypatch):
    from memstara import paths
    local = standalone / 'anil_shared'
    local.mkdir()
    (local / 'SHAP-Interpretation.md').write_text('# External content must not win')
    monkeypatch.setattr(paths, 'WORKSPACE_ROOT', standalone)
    assert catalog.anil_dir() == PACKAGE_ROOT / 'resources/contributed/specialists'
    assert len(catalog.anil_skills()) == 4


def test_explicit_partial_directory_is_not_mixed_with_bundle(standalone, monkeypatch):
    local = standalone / 'chosen'
    local.mkdir()
    (local / 'SHAP-Interpretation.md').write_text('# Explicit current instructions')
    monkeypatch.setenv('MEMSTARA_SPECIALIST_SKILLS_DIR', str(local))
    assert len(catalog.anil_skills()) == 1
    with pytest.raises(FileNotFoundError):
        catalog.resolve('shared-anil-lime')


def test_release_content_and_publication_gates(tmp_path):
    spec = importlib.util.spec_from_file_location('release_check', ROOT / 'scripts/check_release_readiness.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for path in ('src/memstara/resources/contributed', 'deployment', 'examples/research-inputs'):
        # Copy only public config used by this check, never local deployment configs.
        if path == 'deployment':
            (tmp_path / path).mkdir()
            shutil.copyfile(ROOT / path / 'release-readiness.json', tmp_path / path / 'release-readiness.json')
        else:
            shutil.copytree(ROOT / path, tmp_path / path)
    assert module.check(tmp_path) == []
    assert module.check(tmp_path, publication=True)
    skill = tmp_path / 'src/memstara/resources/contributed/specialists/SHAP-Interpretation.md'
    skill.write_text('modified')
    assert any('hash mismatch' in e for e in module.check(tmp_path))
