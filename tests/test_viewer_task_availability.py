"""An unavailable store must not masquerade as a deleted task.

Run with viewer/.venv/bin/python -m unittest discover -s tests
-p test_viewer_task_availability.py; the offline backend suite may lack FastAPI.
"""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

try:
    from fastapi import HTTPException
    from viewer.api import main
except ModuleNotFoundError:
    main = None


@unittest.skipIf(main is None, "Run this contract check in the viewer Python environment")
class TaskAvailabilityTests(unittest.TestCase):
    def test_outage_and_absence_have_different_status(self):
        for healthy, status in [(False, 503), (True, 404)]:
            with self.subTest(healthy=healthy):
                with patch.object(main.scene, "_board", AsyncMock(return_value=[])), patch.object(
                    main, "pools", SimpleNamespace(health=SimpleNamespace(memstara=healthy)),
                ):
                    with self.assertRaises(HTTPException) as raised:
                        asyncio.run(main.task(123))
                    self.assertEqual(raised.exception.status_code, status)

    def test_health_probe_does_not_materialize_execution_history(self):
        connection = AsyncMock()
        async def guarded(store, callback, fallback):
            return await callback(connection)
        with patch.object(main.pools, 'guarded', guarded), patch.object(
            main.scene, '_core_facts', AsyncMock(side_effect=AssertionError('history scan')),
        ):
            asyncio.run(main.health())
        self.assertEqual(connection.fetchval.await_count, 2)
        connection.execute.assert_not_called()
