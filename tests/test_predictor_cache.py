"""Fresh, stale and concurrent semantic-index startup without network or LLMs."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import time

import numpy as np
import pytest

from memstara.predictor_cache import ensure


@pytest.fixture
def cache(tmp_path, monkeypatch):
    from memstara.matcher import config, embedder
    data = tmp_path / 'data.csv'
    data.write_text('age,blood_pressure,target\n20,110,0\n40,140,1\n')
    catalog = tmp_path / 'derived/matcher_catalog.json'
    monkeypatch.setenv('MEMSTARA_DATASET_PATH', str(data))
    monkeypatch.setenv('MEMSTARA_OUTCOME_COLUMN', 'target')
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(catalog.parent))
    monkeypatch.delenv('MEMSTARA_LEAKAGE_RULES_PATH', raising=False)
    monkeypatch.setattr(config, 'CATALOG_JSON', catalog)
    calls = []
    def encoder(_):
        calls.append(True)
        time.sleep(.01)
        return lambda texts: np.ones((len(texts), 8), dtype=np.float32)
    monkeypatch.setattr(embedder, 'sentence_transformer_encoder', encoder)
    monkeypatch.setattr(embedder, 'current_device', lambda: 'cpu')
    return data, catalog, calls


@pytest.mark.parametrize('damage', ['missing', 'catalog', 'matrix', 'receipt', 'header', 'target', 'model'])
def test_cache_build_reuse_and_repair(cache, damage, monkeypatch):
    from memstara.matcher import embedder
    from memstara.matcher.config import RunConfig, EmbeddingConfig
    data, catalog, calls = cache
    assert ensure()['action'] == 'built'
    assert ensure()['action'] == 'reused'
    if damage == 'missing':
        catalog.unlink()
    elif damage == 'catalog':
        catalog.write_text('corrupt')
    elif damage == 'matrix':
        embedder.embeddings_path(catalog).write_bytes(b'broken')
    elif damage == 'receipt':
        catalog.with_suffix('.ready.json').write_text('[]')
    elif damage == 'header':
        data.write_text(data.read_text().replace('age,', 'patient_age,'))
    elif damage == 'target':
        monkeypatch.setenv('MEMSTARA_OUTCOME_COLUMN', 'age')
    else:
        monkeypatch.setattr('memstara.matcher.service.build_run_config',
                            lambda: RunConfig(embedding=EmbeddingConfig(revision='another-revision')))
    assert ensure()['action'] == 'built'
    assert ensure()['action'] == 'reused'
    assert len(calls) == 2


def test_concurrent_preparations_publish_only_one_build(cache):
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(lambda _: ensure(), range(3)))
    assert sorted(r['action'] for r in results) == ['built', 'reused', 'reused']
    assert len(cache[2]) == 1


def test_failed_rebuild_preserves_previous_artifacts_and_can_retry(cache, monkeypatch):
    data, catalog, _ = cache
    ensure()
    previous = {p.name:p.read_bytes() for p in catalog.parent.iterdir() if p.is_file()}
    data.write_text(data.read_text().replace('age,', 'patient_age,'))
    with monkeypatch.context() as context:
        def unavailable(_):
            raise OSError('Embedding model is unavailable offline')
        context.setattr('memstara.matcher.embedder.sentence_transformer_encoder', unavailable)
        with pytest.raises(OSError, match='unavailable'):
            ensure()
    assert all((catalog.parent / name).read_bytes() == value for name, value in previous.items())
    assert ensure()['action'] == 'built'


@pytest.mark.parametrize('use_okf', [False, True])
def test_readiness_builds_missing_cache_before_validation(cache, monkeypatch, tmp_path, use_okf):
    from memstara.pipeline import board
    monkeypatch.setenv('AGENTIC_OKF_BUNDLE_DIR', str(tmp_path))
    monkeypatch.setenv('MOTORO_DATABASE_URL', 'postgresql://fixture')
    class Connection:
        async def close(self):
            pass
    async def connect(_):
        return Connection()
    monkeypatch.setattr(board.asyncpg, 'connect', connect)
    monkeypatch.setattr(board, 'dsn', lambda:'postgresql://fixture')
    run_dir = tmp_path / 'run'
    run_dir.mkdir()
    (run_dir / 'progress.json').write_text(json.dumps({'iteration': 3, 'counts': {'done': 2}}))
    assert asyncio.run(board.check_environment(y_column='target', use_okf=use_okf,
                                               prepare_matcher=True, run_dir=run_dir)) == []
    assert cache[1].exists()
    assert json.loads((run_dir / 'progress.json').read_text())['counts'] == {'done': 2}
    assert json.loads((run_dir / 'progress.json').read_text())['preparation']['status'] == 'completed'


def test_preparation_failure_is_recorded_before_agents(cache, monkeypatch, tmp_path):
    from memstara.pipeline import board
    monkeypatch.setenv('MOTORO_DATABASE_URL', 'postgresql://fixture')
    class Connection:
        async def close(self):
            pass
    async def connect(_):
        return Connection()
    monkeypatch.setattr(board.asyncpg, 'connect', connect)
    monkeypatch.setattr(board, 'dsn', lambda:'postgresql://fixture')
    def unavailable(_):
        raise OSError('embedding download interrupted')
    monkeypatch.setattr('memstara.matcher.embedder.sentence_transformer_encoder', unavailable)
    run_dir = tmp_path / 'run'
    problems = asyncio.run(board.check_environment(y_column='target', use_okf=False,
                                                    prepare_matcher=True, run_dir=run_dir))
    assert len(problems) == 1 and 'download interrupted' in problems[0]
    assert json.loads((run_dir / 'progress.json').read_text())['preparation']['status'] == 'failed'
