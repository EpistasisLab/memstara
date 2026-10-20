"""Console failures are recorded without repeating successful agent work."""
import json
from unittest.mock import AsyncMock

import pytest

from memstara.pipeline import reporting


@pytest.mark.asyncio
async def test_console_permission_failure_records_warning_and_returns(tmp_path):
    entry = {'seq': 4, 'stage': 'interpret#1', 'status': 'completed'}
    operation = AsyncMock(side_effect=PermissionError(13, 'private value'))
    await reporting.show_console_summary(operation, entry, tmp_path)
    operation.assert_awaited_once_with(entry)
    raw = (tmp_path / '04_console_warning.json').read_text()
    assert json.loads(raw)['status'] == 'console_unavailable'
    assert 'private value' not in raw
    assert entry['status'] == 'completed'


@pytest.mark.asyncio
async def test_diagnostic_storage_failure_is_not_silently_ignored(tmp_path, monkeypatch):
    def unavailable(*args, **kwargs):
        raise PermissionError('diagnostic storage unavailable')
    monkeypatch.setattr(reporting, 'atomic_json', unavailable)
    with pytest.raises(PermissionError, match='diagnostic storage'):
        await reporting.show_console_summary(AsyncMock(side_effect=BrokenPipeError()),
                                            {'seq': 1, 'stage': 'ml'}, tmp_path)


@pytest.mark.asyncio
async def test_programming_error_is_not_classified_as_console_failure(tmp_path):
    with pytest.raises(ValueError):
        await reporting.show_console_summary(AsyncMock(side_effect=ValueError()),
                                            {'seq': 1, 'stage': 'ml'}, tmp_path)
