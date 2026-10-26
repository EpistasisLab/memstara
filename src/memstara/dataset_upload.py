"""CSV upload boundary: decode -> inspect -> persist unchanged bytes.

No client-supplied path is used for storage. Inspection returns column metadata
and aggregate counts, never patient rows. Registration/target validation remains
in research_inputs; uploading alone never authorizes an experiment.
"""
import base64
import binascii
import csv
import hashlib
import io
import math
import uuid
from collections import Counter
from typing import Any, TypedDict

from memstara.research_inputs import MISSING, registry_root

MAX_UPLOAD = 5 * 1024 * 1024
MAX_REQUEST_BYTES = 7_100_000


class CsvInspection(TypedDict):
    columns: list[str]
    rows: int
    columns_with_missing: dict[str, int]
    missing_cells: int
    nonfinite_columns: list[str]
    nonnumeric_columns: list[str]


def decode_upload(body: dict[str, Any]) -> bytes:
    """Reject oversized or invalid transport before parsing or writing a file."""
    if set(body) != {'filename', 'content_base64'}:
        raise ValueError('Supply a CSV filename and base64 file content')
    filename = body['filename']
    if not isinstance(filename, str) or not filename.lower().endswith('.csv'):
        raise ValueError('Choose a CSV file')
    encoded = body['content_base64']
    if not isinstance(encoded, str) or len(encoded) > (MAX_UPLOAD + 2) // 3 * 4:
        raise ValueError('CSV upload limit is 5 MiB')
    try:
        raw = base64.b64decode(encoded, validate=True)
        text = raw.decode('utf-8-sig')
    except (ValueError, UnicodeError, binascii.Error):
        raise ValueError('Upload a UTF-8 encoded CSV file') from None
    if not raw or len(raw) > MAX_UPLOAD or '\x00' in text:
        raise ValueError('Upload a non-empty UTF-8 CSV, at most 5 MiB')
    return raw


def inspect_csv(raw: bytes) -> CsvInspection:
    """Inspect without target assumptions, imputation, or source modification."""
    missing: Counter[str] = Counter()
    nonfinite: Counter[str] = Counter()
    nonnumeric: Counter[str] = Counter()
    rows = 0
    try:
        reader = csv.reader(io.StringIO(raw.decode('utf-8-sig')), strict=True)
        headers = next(reader, [])
        if not headers or any(not h.strip() for h in headers) or len(set(headers)) != len(headers):
            raise ValueError('CSV headers must be non-empty and unique')
        for row in reader:
            if len(row) != len(headers):
                raise ValueError('CSV rows must have the same number of fields as the header')
            rows += 1
            for column, value in zip(headers, row, strict=True):
                if value.strip().lower() in MISSING:
                    missing[column] += 1
                    continue
                try:
                    if not math.isfinite(float(value)):
                        nonfinite[column] += 1
                except ValueError:
                    nonnumeric[column] += 1
    except csv.Error:
        raise ValueError('CSV cannot be parsed; check quoting and field sizes') from None
    if not rows:
        raise ValueError('CSV has no data rows')
    return {
        'columns': headers,
        'rows': rows,
        'columns_with_missing': dict(missing),
        'missing_cells': sum(missing.values()),
        'nonfinite_columns': list(nonfinite),
        'nonnumeric_columns': list(nonnumeric),
    }


def upload(body: dict[str, Any]) -> dict[str, Any]:
    """Publish only a structurally valid CSV under a generated private directory."""
    raw = decode_upload(body)
    inspection = inspect_csv(raw)
    directory = registry_root() / 'uploads' / uuid.uuid4().hex
    directory.mkdir(parents=True, mode=0o700)
    destination = directory / 'dataset.csv'
    try:
        # Set permissions on creation, rather than after writing sensitive bytes.
        import os
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(raw)
    except OSError:
        destination.unlink(missing_ok=True)
        directory.rmdir()
        raise
    return {
        **inspection,
        'dataset_path': str(destination.resolve()),
        'sha256': hashlib.sha256(raw).hexdigest(),
        'original_preserved': True,
        'message': (
            'Missing values found. Execution is blocked. Correct the CSV and upload it again; no values or rows were changed.'
            if inspection['missing_cells'] else
            'No missing values found. Select a target and validate before execution.'
        ),
    }
