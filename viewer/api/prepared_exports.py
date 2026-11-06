"""Report export preparation separately from binary transfer, across API workers.

Only private temporary download files are written. Experiment files and databases
are never changed. A short-lived opaque receipt lets a different worker serve the
finished file without rebuilding it or holding its contents in browser memory.
"""
import asyncio
from contextlib import suppress
import json
import logging
import os
from pathlib import Path
import re
import tempfile
import threading
import time
import uuid

from fastapi import HTTPException
from fastapi.responses import FileResponse, StreamingResponse
from export_files import build_file, _preparation_lock
from linked_outputs import bundle

ROOT = Path(tempfile.gettempdir()) / 'memstara-prepared-exports'
TTL = 1800
HEARTBEAT = 10
PREPARATION_LIMIT = 900
logger = logging.getLogger('uvicorn.error.viewer')


def directory():
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    return ROOT


def cleanup():
    cutoff = time.time() - TTL
    for path in directory().iterdir():
        if re.fullmatch(r'[0-9a-f]{32}\.(json|bin|part)', path.name):
            with suppress(FileNotFoundError):
                if path.stat().st_mtime < cutoff:
                    path.unlink()


def forget(identifier):
    for suffix in ('json', 'bin', 'part'):
        (ROOT / f'{identifier}.{suffix}').unlink(missing_ok=True)


def save(identifier, value, kind, report, cancelled):
    target, size = build_file(value, kind, report, cancelled)
    try:
        if cancelled.is_set():
            raise InterruptedError('Export cancelled')
        path = directory() / f'{identifier}.part'
        with path.open('xb') as output:
            os.chmod(path, 0o600)
            while chunk := target.read(1024 * 1024):
                if cancelled.is_set():
                    raise InterruptedError('Export cancelled')
                output.write(chunk)
        os.replace(path, ROOT / f'{identifier}.bin')
        receipt = {'kind': kind, 'bytes': size, 'results': len(value['results']),
                   'executions': len(value['run_tags']), 'warnings': len(value['warnings']),
                   'expires_at': time.time() + TTL}
        (ROOT / f'{identifier}.json').write_text(json.dumps(receipt))
        return receipt
    finally:
        target.close()


async def prepare(tags, kind):
    if kind not in ('table', 'zip'):
        raise HTTPException(422, 'Unsupported prepared export format')
    if _preparation_lock.locked():
        raise HTTPException(429, 'Another export is being prepared. Please wait and retry.')
    identifier = uuid.uuid4().hex
    cancelled = threading.Event()
    events = asyncio.Queue()
    loop = asyncio.get_running_loop()
    current = {'message': 'Starting export preparation', 'progress': {'phase': 'preparing'}}

    def report(message, completed=None, total=None):
        progress = {'phase': 'preparing'}
        if completed is not None and total is not None and total > 0:
            progress.update(completedUnits=completed, totalUnits=total)
        event = {'type': 'progress', 'message': message, 'progress': progress}
        def publish():
            current.update(message=message, progress=progress)
            events.put_nowait(event)
        loop.call_soon_threadsafe(publish)

    async def work():
        async with _preparation_lock:
            await asyncio.to_thread(cleanup)
            value = await bundle(tags, kind == 'zip', on_progress=report)
            report('Formatting summary CSV' if kind == 'table' else 'Preparing linked ZIP files')
            writer = asyncio.create_task(asyncio.to_thread(save, identifier, value, kind, report, cancelled))
            try:
                return await asyncio.shield(writer)
            except asyncio.CancelledError:
                cancelled.set()
                with suppress(Exception):
                    await writer
                raise

    async def stream():
        task = asyncio.create_task(work())
        ready = False
        started = time.monotonic()
        encode = lambda value: (json.dumps(value) + '\n').encode()
        try:
            yield encode({'type': 'progress', **current})
            while True:
                if time.monotonic() - started > PREPARATION_LIMIT:
                    raise TimeoutError('Export preparation exceeded its limit')
                while not events.empty():
                    yield encode(events.get_nowait())
                if task.done():
                    receipt = await task
                    ready = True
                    logger.info('Prepared export ready: id=%s format=%s bytes=%d seconds=%.2f',
                                identifier, kind, receipt['bytes'], time.monotonic() - started)
                    yield encode({'type': 'ready', 'download_url': f'/api/experiments/prepared-file/{identifier}', **receipt})
                    break
                try:
                    event = await asyncio.wait_for(events.get(), timeout=HEARTBEAT)
                    yield encode(event)
                except TimeoutError:
                    # A heartbeat confirms the server is connected; it does not
                    # increment completion counts or invent a percentage.
                    yield encode({'type': 'progress', **current, 'heartbeat': True})
        except Exception as error:
            logger.warning('Export preparation failed: id=%s format=%s error_type=%s', identifier, kind, type(error).__name__)
            message = str(error.detail) if isinstance(error, HTTPException) else (
                'Export preparation exceeded 15 minutes. No partial file was downloaded.'
                if isinstance(error, TimeoutError) else 'The export could not be prepared. Saved results are unchanged.')
            yield encode({'type': 'error', 'message': message})
        finally:
            if not ready:
                cancelled.set()
                task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await task
                await asyncio.to_thread(forget, identifier)

    return StreamingResponse(stream(), media_type='application/x-ndjson',
        headers={'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no'})


def download(identifier):
    if not re.fullmatch(r'[0-9a-f]{32}', identifier):
        raise HTTPException(404, 'Prepared download not found')
    try:
        receipt = json.loads((ROOT / f'{identifier}.json').read_text())
        path = ROOT / f'{identifier}.bin'
        if receipt['expires_at'] <= time.time():
            raise HTTPException(410, 'This prepared download expired. Prepare the export again.')
        if path.stat().st_size != receipt['bytes']:
            raise HTTPException(503, 'The prepared file is incomplete. No substitute file was downloaded.')
    except (FileNotFoundError, ValueError, KeyError):
        raise HTTPException(404, 'Prepared download not found. Prepare the export again.') from None
    kind = receipt['kind']
    return FileResponse(path, media_type='application/zip' if kind == 'zip' else 'text/csv',
        filename='linked-results.zip' if kind == 'zip' else 'hypothesis-skill-table.csv',
        headers={'Cache-Control': 'no-store', 'X-Memstara-Export-Bytes': str(receipt['bytes']),
                 **{'X-Memstara-Export-' + key.title(): str(receipt[key]) for key in ('results', 'executions', 'warnings')}})
