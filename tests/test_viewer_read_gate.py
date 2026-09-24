import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer/api'))
from read_gate import shared_read


def test_concurrent_readers_share_work_and_cancel_independently():
    async def check():
        entered=asyncio.Event(); release=asyncio.Event(); calls=0
        async def read():
            nonlocal calls
            calls+=1; entered.set(); await release.wait(); return {'value': 42}
        first=asyncio.create_task(shared_read('same', read))
        await entered.wait()
        second=asyncio.create_task(shared_read('same', read))
        await asyncio.sleep(0)
        first.cancel()
        try: await first
        except asyncio.CancelledError: pass
        release.set()
        assert await second == {'value':42}
        assert calls==1
    asyncio.run(check())


def test_distinct_scopes_do_not_saturate_database():
    async def check():
        active=0; peak=0
        async def read(value):
            nonlocal active,peak
            active+=1; peak=max(peak,active)
            await asyncio.sleep(.01); active-=1
            return value
        results=await asyncio.gather(*(shared_read(n,lambda n=n:read(n)) for n in range(8)))
        assert results==list(range(8))
        assert peak==1
    asyncio.run(check())


def test_finished_read_survives_disconnected_browser():
    async def check():
        release=asyncio.Event(); calls=0
        async def read():
            nonlocal calls
            calls+=1; await release.wait(); return 7
        waiter=asyncio.create_task(shared_read('archive',read))
        await asyncio.sleep(0); await asyncio.sleep(0)
        waiter.cancel()
        try:await waiter
        except asyncio.CancelledError:pass
        release.set()
        await asyncio.sleep(.01)
        assert await shared_read('archive',read)==7
        assert calls==1
    asyncio.run(check())


def test_statement_timeout_does_not_destroy_other_readers_pool():
    import asyncpg
    from unittest.mock import AsyncMock, MagicMock
    from db import Pools
    async def check():
        pools=Pools();pool=MagicMock();scope=MagicMock()
        scope.__aenter__=AsyncMock(return_value=object());scope.__aexit__=AsyncMock(return_value=False)
        pool.acquire.return_value=scope;pools._pool=AsyncMock(return_value=pool);pools._discard=AsyncMock()
        async def slow(conn):raise asyncpg.QueryCanceledError('statement timeout')
        assert await pools.guarded('core',slow,[])==[]
        pools._discard.assert_not_called()
        async def healthy(conn):return ['available']
        assert await pools.guarded('core',healthy,[])==['available']
        assert pools.health.core is True
    asyncio.run(check())
