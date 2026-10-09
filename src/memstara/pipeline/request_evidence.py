"""Private, durable application-service payload evidence; never raw HTTP headers."""
import dataclasses
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from uuid import UUID

from memstara.pipeline.diagnostics import call_loop, request_id


def normalize(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return normalize(value.value)
    if hasattr(value, 'model_dump') and not isinstance(value, type):
        return normalize(value.model_dump(mode='json'))
    if isinstance(value, type) and hasattr(value, 'model_json_schema'):
        return {'schema': normalize(value.model_json_schema())}
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return normalize(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(k): normalize(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [normalize(v) for v in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    # Motoro's public run/step readers return ORM records, not Pydantic schemas.
    # Export only mapped columns, never relationships or arbitrary object reprs.
    try:
        from sqlalchemy import inspect
    except ImportError:
        pass
    else:
        mapped = inspect(value, raiseerr=False)
        if mapped is not None and hasattr(mapped, 'mapper'):
            return {column.key: normalize(getattr(value, column.key)) for column in mapped.mapper.column_attrs}
    raise TypeError('Unsupported evidence value')


def redact(value):
    """Remove credential fields and configured secret values, including echoed JSON."""
    secrets = [v for k, v in os.environ.items() if v and len(v) >= 8
               and k.upper().endswith(('_API_KEY', '_SECRET', '_TOKEN', '_PASSWORD', '_DSN'))]

    def walk(item):
        if isinstance(item, dict):
            return {k: '[REDACTED]' if re.search(
                r'(?i)(api[-_]?key|authorization|password|secret|access[-_]?token|refresh[-_]?token)', k)
                    else walk(v) for k, v in item.items()}
        if isinstance(item, list):
            return [walk(v) for v in item]
        if isinstance(item, str):
            try:
                parsed = json.loads(item)
            except ValueError:
                parsed = None
            if isinstance(parsed, (dict, list)):
                return json.dumps(walk(parsed), ensure_ascii=False)
            for secret in secrets:
                item = item.replace(secret, '[REDACTED]')
            item = re.sub(r'(?i)\bBearer\s+[^\s"\']+', 'Bearer [REDACTED]', item)
            return re.sub(r'://[^/\s:@]+:[^@\s]+@', '://[REDACTED]@', item)
        return item

    return walk(normalize(value))


def save(context, kind, payload):
    """Return an integrity reference, or visibly mark incomplete coverage without replay."""
    if context is None:
        return None
    try:
        identity = str(UUID(request_id.get()))
        if kind not in ('input', 'output', 'failure'):
            raise ValueError('Unknown evidence kind')
        relative = Path('model_io') / f'{identity}.{kind}.json'
        path = Path(context[0]) / relative
        row = {'schema_version': 1, 'request_id': identity, 'run_id': str(context[1]),
               'stage': context[2], 'loop': call_loop.get(), 'kind': kind,
               'scope': 'application_service', 'payload': redact(payload)}
        return {'path': relative.as_posix(), 'kind': kind, **write_private(path, row)}
    except (OSError, TypeError, ValueError):
        logging.getLogger(__name__).warning(
            'Model payload evidence write failed; input/output audit is incomplete')
        return None


def write_private(path, value):
    """Atomically persist normalized/redacted evidence, raising on incomplete writes."""
    path = Path(path)
    path.parent.mkdir(mode=0o700, exist_ok=True)
    raw = json.dumps(redact(value), ensure_ascii=False, allow_nan=False).encode('utf-8')
    temporary = path.with_suffix('.tmp')
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
