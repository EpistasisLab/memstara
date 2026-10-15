"""A stale predictor-mapping cache must stop the run before agent calls."""

import csv

import pytest

from memstara.matcher import catalog
from memstara.pipeline import board


@pytest.mark.asyncio
async def test_dataset_pipeline_rejects_stale_matcher_before_execution(monkeypatch, tmp_path):
    dataset = tmp_path / 'cohort.csv'
    with dataset.open('w', newline='') as stream:
        csv.writer(stream).writerow(['age', 'outcome'])
    monkeypatch.setenv('AGENTIC_OKF_BUNDLE_DIR', str(tmp_path))
    monkeypatch.setenv('MEMSTARA_DATASET_PATH', str(dataset))
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path / 'output'))
    monkeypatch.setenv('MOTORO_DATABASE_URL', 'postgresql://test')
    monkeypatch.setenv('MEMSTARA_OUTCOME_COLUMN', 'outcome')

    class Connection:
        async def close(self):
            pass

    async def connect(_dsn):
        return Connection()

    monkeypatch.setattr(board.asyncpg, 'connect', connect)
    monkeypatch.setattr(board, 'dsn', lambda: 'postgresql://test')
    monkeypatch.setattr(catalog, 'verify_catalog', lambda *_args: 'catalog was built for another cohort')

    problems = await board.check_environment(y_column='outcome')

    assert any('Predictor-mapping cache is not ready' in item and 'another cohort' in item
               for item in problems)


@pytest.mark.asyncio
async def test_proposal_pipeline_does_not_require_dataset_matcher(monkeypatch, tmp_path):
    monkeypatch.delenv('AGENTIC_OKF_BUNDLE_DIR', raising=False)
    monkeypatch.delenv('MEMSTARA_DATASET_PATH', raising=False)
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    monkeypatch.setenv('MOTORO_DATABASE_URL', 'postgresql://test')

    class Connection:
        async def close(self):
            pass

    async def connect(_dsn):
        return Connection()

    monkeypatch.setattr(board.asyncpg, 'connect', connect)
    monkeypatch.setattr(board, 'dsn', lambda: 'postgresql://test')

    problems = await board.check_environment(use_okf=False, use_data=False)

    assert not any('Predictor-mapping' in item for item in problems)
