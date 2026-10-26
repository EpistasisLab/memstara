"""Run paid acceptance inside the application network, without restarting it."""
import asyncio
import os
import subprocess
import sys

import asyncpg


async def check_databases():
    for key in ('MEMSTARA_DATABASE_URL', 'MOTORO_DATABASE_URL'):
        value = os.environ.get(key, '').replace('postgresql+asyncpg://', 'postgresql://', 1)
        if not value:
            raise RuntimeError(f'{key} is absent from generated service settings')
        try:
            connection = await asyncpg.connect(value, timeout=10)
            await connection.execute('SELECT 1')
            await connection.close()
        except Exception:
            raise RuntimeError(f'{key} is unavailable inside the application network; '
                               'start the application and check its database health') from None


def main():
    try:
        asyncio.run(check_databases())
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print('Database connections verified. Starting one paid Haiku pipeline with synthetic inputs. '
          'Existing experiments are not restarted. Evidence is retained under outputs/verification.', flush=True)
    return subprocess.call([
        sys.executable, '-m', 'pytest', 'tests/live/test_haiku_pipeline.py',
        '--run-live', '-k', 'synthetic-okf-dataset', '--live-loops=1', '--live-audit-io',
        '-s', '-q', '--tb=short',
    ])


if __name__ == '__main__':
    raise SystemExit(main())
