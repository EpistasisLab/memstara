"""Stream lossless linked evidence into private temporary downloads.

The viewer database remains SELECT-only. Temporary files are unlinked immediately
by TemporaryFile and closed after delivery; no experiment artifact is changed.
CSV columns follow the existing browser exports, with nested values as JSON cells.
"""
import asyncio
import gzip
import json
import logging
import math
import re
import shutil
import tempfile
import time
import zipfile

from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

CHILDREN = ('agents', 'results', 'costs', 'artifacts')
ENCODER = json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(',', ':'))
PRETTY = json.JSONEncoder(ensure_ascii=False, allow_nan=False, indent=2)
logger = logging.getLogger('uvicorn.error.viewer')
_preparation_lock = asyncio.Lock()
SUMMARY_HEADERS = ['Hypothesis Skill', 'Pipeline', 'Run Tag', 'Scheduled Replicate',
    'Evaluation Replicate', 'Result ID', 'Task ID', 'Trial', 'Subjects', 'N Train', 'N Test',
    'Seed', 'Model', 'AUROC', 'Average Precision', 'F1', 'Threshold', 'Sensitivity',
    'Specificity', 'Precision', 'TN', 'FP', 'FN', 'TP', 'Hypothesis', 'result_uid',
    'Pipeline Number', 'Schedule Replicate', 'interpretation_output_ids',
    'explanation_output_ids', 'interpretation_status', 'explanation_status']
EVIDENCE_HEADERS = ['schema_version', 'record_type', 'record_index', 'run_tag',
    'experiment_id', 'combination_id', 'pipeline_id', 'execution_status', 'synced_at',
    'result_id', 'task_id', 'trial', 'hypothesis_id', 'stage', 'agent_run_id', 'agent_skill',
    'skills_json', 'model', 'seed_number', 'replicate_seeds', 'auroc', 'average_precision',
    'threshold', 'sensitivity', 'specificity', 'precision', 'f1', 'true_negative',
    'false_positive', 'false_negative', 'true_positive', 'hypothesis', 'perspective',
    'y_column', 'interpretation', 'created_at', 'started_at', 'duration_seconds', 'path',
    'sha256', 'bytes', 'kind', 'result_uid', 'pipeline_number', 'replicate_number',
    'interpretation_output_ids', 'explanation_output_ids', 'interpretation_status', 'explanation_status']
RECORD_FIELDS = ['run_tag', 'result_uid', 'result_id', 'task_id', 'trial', 'pipeline_number',
    'replicate_number', 'interpretation_status', 'explanation_status', 'hypothesis_id',
    'hypothesis', 'perspective', 'y_column', 'model', 'interpretation', 'created_at',
    'agent_run_id', 'stage', 'started_at', 'duration_seconds', 'path', 'sha256', 'bytes', 'kind']
ALIASES = {
    'seed_number': [('evaluation', 'data_allocation', 'effective_plan', 'seed'),
        ('evaluation', 'data_allocation', 'plan', 'seed'), ('evaluation', 'data_allocation', 'seed'),
        ('evaluation', 'evaluation', 'replicates', 0, 'seed'), ('evaluation', 'seed'), ('seed',)],
    'replicate_seeds': [('evaluation', 'evaluation', 'replicate_seeds'), ('evaluation', 'replicate_seeds')],
    'auroc': [('auc',), ('evaluation', 'auc'),
        ('evaluation', 'evaluation', 'replicates', 0, 'performance', 'test', 'metrics', 'auroc'),
        ('evaluation', 'evaluation', 'replicates', 0, 'auc')],
}
for _name, _legacy in [('average_precision', 'average_precision'), ('f1', 'f1'),
    ('threshold', 'operating_point.probability_cutoff'), ('sensitivity', 'operating_point.sensitivity'),
    ('specificity', 'operating_point.specificity'), ('precision', 'operating_point.precision'),
    ('true_negative', 'operating_point.true_negative'), ('false_positive', 'operating_point.false_positive'),
    ('false_negative', 'operating_point.false_negative'), ('true_positive', 'operating_point.true_positive')]:
    _base = ('evaluation', 'evaluation', 'replicates', 0)
    _modern = ('performance', 'test', 'confusion_matrix', {
        'true_negative': 'tn', 'false_positive': 'fp', 'false_negative': 'fn', 'true_positive': 'tp'}[_name]) if _name.startswith(('true_', 'false_')) else (
            ('performance', 'test', 'threshold') if _name == 'threshold' else ('performance', 'test', 'metrics', _name))
    ALIASES[_name] = [_base + _modern, _base + tuple(_legacy.split('.'))]


def obj(value):
    return value if isinstance(value, dict) else {}


def at(value, path):
    for part in path:
        if isinstance(part, int):
            value = value[part] if isinstance(value, list) and 0 <= part < len(value) else None
        else:
            value = obj(value).get(part)
    return value


def first(*values):
    return next((value for value in values if value is not None), None)


def number(value):
    return value if type(value) in (int, float) and math.isfinite(value) else None


def text(value):
    return value if isinstance(value, str) else ''


def write_json(target, value):
    for chunk in PRETTY.iterencode(value):
        target.write(chunk.encode('utf-8'))
    target.write(b'\n')


def write_row(target, values):
    """Write each quoted cell incrementally, including very large nested JSON."""
    for index, value in enumerate(values):
        if index:
            target.write(b',')
        target.write(b'"')
        if isinstance(value, (dict, list)):
            chunks = ENCODER.iterencode(value)
        else:
            rendered = '' if value is None else ENCODER.encode(value) if isinstance(value, bool) else str(value)
            if re.match(r'^[\t\r ]*[=+\-@]', rendered):
                target.write(b"'")
            chunks = (rendered,)
        for chunk in chunks:
            for start in range(0, len(chunk), 65536):
                target.write(chunk[start:start + 65536].replace('"', '""').encode('utf-8'))
        target.write(b'"')
    target.write(b'\r\n')


def summary_rows(results):
    rows = []
    for result in results:
        measured = obj(result.get('evaluation'))
        evaluation = obj(measured.get('evaluation'))
        skills = obj(measured.get('skills')).get('hypothesis')
        skills = skills if isinstance(skills, list) else []
        skill = ', '.join(filter(None, map(text, skills))) or text(result.get('hypothesis_id')) or 'Not recorded'
        fits = evaluation.get('replicates')
        fits = (fits if isinstance(fits, list) else []) or [{'auc': result.get('auc'), 'seed': measured.get('seed'),
            'n_train': measured.get('n_train'), 'n_test': measured.get('n_test')}]
        for index, raw in enumerate(fits):
            fit = obj(raw)
            test = obj(at(fit, ('performance', 'test')))
            metrics, matrix, point = obj(test.get('metrics')), obj(test.get('confusion_matrix')), obj(fit.get('operating_point'))
            threshold = first(number(test.get('threshold')), number(point.get('probability_cutoff')))
            parameters = obj(fit.get('parameters'))
            preferred = ['penalty', 'solver', 'C', 'class_weight', 'n_estimators', 'max_depth', 'learning_rate']
            keys = [key for key in preferred if key in parameters] + sorted(key for key in parameters if key not in preferred)
            parts = [f'{key}={ENCODER.encode(parameters[key])}' for key in keys] or ['parameters not recorded']
            if threshold is not None:
                parts.append(f'threshold={threshold}')
            model = (text(measured.get('model')) or 'Model not recorded') + ' (' + '; '.join(parts) + ')'
            train, test_count = number(fit.get('n_train')), number(fit.get('n_test'))
            row = [skill, text(result.get('pipeline_name')) or text(result.get('run_tag')) or 'Analysis',
                text(result.get('run_tag')), number(result.get('iteration')), index + 1,
                number(result.get('result_id')), number(result.get('task_id')), number(result.get('trial')),
                train + test_count if train is not None and test_count is not None else None, train, test_count,
                first(number(fit.get('seed')), number(measured.get('seed'))), model,
                first(number(metrics.get('auroc')), number(fit.get('auc')), number(result.get('auc'))),
                first(number(metrics.get('average_precision')), number(fit.get('average_precision'))),
                first(number(metrics.get('f1')), number(fit.get('f1'))), threshold,
                *[first(number(metrics.get(key)), number(point.get(key))) for key in ('sensitivity', 'specificity', 'precision')],
                *[first(number(matrix.get(short)), number(point.get(long))) for short, long in
                  [('tn', 'true_negative'), ('fp', 'false_positive'), ('fn', 'false_negative'), ('tp', 'true_positive')]],
                text(result.get('hypothesis')), text(result.get('result_uid')), number(result.get('pipeline_number')),
                number(result.get('replicate_number')), result.get('interpretation_output_ids', []),
                result.get('explanation_output_ids', []), text(result.get('interpretation_status')) or 'not_loaded',
                text(result.get('explanation_status')) or 'not_loaded']
            rows.append(row)
    return sorted(rows, key=lambda row: (row[0].casefold(), row[1].casefold(),
        row[3] if row[3] is not None else math.inf, row[4]))


def write_summary(target, results):
    target.write(b'\xef\xbb\xbf')
    write_row(target, SUMMARY_HEADERS)
    for row in summary_rows(results):
        write_row(target, row)


def evidence_rows(details):
    for detail in details:
        base = {key: detail.get(key) for key in ('run_tag', 'experiment_id', 'combination_id', 'pipeline_id', 'synced_at')}
        base.update(schema_version='memstara_complete_evidence_csv_v1', execution_status=detail.get('status'))
        groups = [('execution', [{key: value for key, value in detail.items() if key not in CHILDREN}])]
        groups += [(name[:-1], detail.get(name) or []) for name in CHILDREN]
        for kind, records in groups:
            for index, record in enumerate(records):
                row = {**base, 'record_type': kind, 'record_index': index}
                if isinstance(record, dict):
                    for key in RECORD_FIELDS:
                        if key in record and not isinstance(record[key], (dict, list)):
                            row[key] = record[key]
                    if kind == 'result':
                        for key in ('interpretation_output_ids', 'explanation_output_ids'):
                            if isinstance(record.get(key), list):
                                row[key] = record[key]
                        row.update({key: first(*(at(record, path) for path in paths)) for key, paths in ALIASES.items()})
                        row['skills_json'] = first(at(record, ('evaluation', 'skills')), record.get('skills'))
                    if kind == 'agent':
                        row['agent_skill'] = first(*(at(record, path) for path in [('playbook',), ('skill',),
                            ('metadata', 'playbook'), ('metadata', 'skill'), ('evidence', 'playbook'), ('evidence', 'skill')]))
                    row.update({'record.' + key: value for key, value in record.items()})
                    if not record:
                        row['record'] = '{}'
                else:
                    row['record'] = record
                yield row


def write_evidence(target, details):
    keys = set()
    for row in evidence_rows(details):
        keys.update(row)
    headers = [key for key in EVIDENCE_HEADERS if key in keys] + sorted(keys.difference(EVIDENCE_HEADERS))
    target.write(b'\xef\xbb\xbf')
    write_row(target, headers)
    for row in evidence_rows(details):
        write_row(target, (row.get(key) for key in headers))


def manifest(bundle):
    return {key: bundle[key] for key in ('schema_version', 'generated_at', 'requested_run_tags', 'run_tags', 'warnings')} | {
        'counts': {key: len(bundle[key]) for key in ('results', 'interpretations', 'explanations')} | {
            'unlinked_explanations': sum(not item['result_uids'] for item in bundle['explanations'])},
        'relationships': {'result_key': 'result_uid', 'output_key': 'output_id',
            'interpretation_foreign_keys': 'interpretation_output_ids', 'explanation_foreign_keys': 'explanation_output_ids'}}


def build_file(bundle, format, progress=None, cancelled=None):
    class CheckedWriter:
        def __init__(self, output):
            self.output = output

        def write(self, data):
            if cancelled is not None and cancelled.is_set():
                raise InterruptedError('Export cancelled')
            return self.output.write(data)

    target = tempfile.TemporaryFile()
    try:
        if format == 'table':
            write_summary(CheckedWriter(target), bundle['results'])
            if progress:
                progress('Formatting summary CSV', 1, 1)
        elif format == 'complete':
            write_evidence(CheckedWriter(target), bundle['executions'])
        elif format == 'zip':
            with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
                completed = 0
                def put(name, writer, value):
                    nonlocal completed
                    if progress:
                        progress('Preparing ZIP: ' + name, completed, 8)
                    with archive.open(name, 'w', force_zip64=True) as entry:
                        writer(CheckedWriter(entry), value)
                    completed += 1
                    if progress:
                        progress('Preparing ZIP: ' + name, completed, 8)
                put('results.csv', write_summary, bundle['results'])
                for name in ('results', 'interpretations', 'explanations'):
                    put(name + '.json', write_json, bundle[name])
                put('complete_evidence.csv', write_evidence, bundle['executions'])
                put('complete_evidence.json', write_json, bundle['executions'])
                put('manifest.json', write_json, manifest(bundle))
                archive.writestr('README.txt', 'Linked experiment results and agent outputs\n\n'
                    'All original execution IDs, saved result metadata and complete evidence are included.\n'
                    'Join results.csv/result_uid to output_id in interpretations.json and explanations.json using\n'
                    'interpretation_output_ids and explanation_output_ids; reverse links are result_uids.\n'
                    'Narratives are verbatim JSON strings. Missing/ambiguous links remain explicit in the manifest.\n'
                    'Multiple model fits can share one saved result and its agent output IDs.\n'
                    'No new model calls or experiments were started. CSV has formula-safe quoted cells.\n')
                if progress:
                    progress('ZIP files assembled', 8, 8)
        else:
            raise ValueError('Unsupported linked download format')
        size = target.tell()
        target.seek(0)
        return target, size
    except BaseException:
        target.close()
        raise


def accepts_gzip(value):
    """Honor explicit gzip refusal, even when a wildcard accepts other encodings."""
    qualities = {}
    for item in value.lower().split(','):
        parts = [part.strip() for part in item.split(';')]
        quality = 1.0
        for parameter in parts[1:]:
            if parameter.startswith('q='):
                try:
                    quality = float(parameter[2:])
                except ValueError:
                    quality = 0.0
        qualities[parts[0]] = quality
    return 0 < qualities.get('gzip', qualities.get('*', 0)) <= 1


def compress_csv(source):
    """Compress transport bytes without materializing or changing the original CSV."""
    target = tempfile.TemporaryFile()
    try:
        with gzip.GzipFile(fileobj=target, mode='wb', compresslevel=1, mtime=0) as compressed:
            shutil.copyfileobj(source, compressed, length=1024 * 1024)
        size = target.tell()
        target.seek(0)
        return target, size
    except BaseException:
        target.close()
        raise
    finally:
        source.close()


async def download(tags, format, gzip_csv=False):
    # A second large snapshot must not multiply preparation memory in this worker.
    if _preparation_lock.locked():
        raise HTTPException(429, 'Another full-evidence export is being prepared. Please wait and retry.',
                            headers={'Retry-After': '10'})
    async with _preparation_lock:
        return await _download(tags, format, gzip_csv)


async def _download(tags, format, gzip_csv=False):
    from linked_outputs import bundle
    started = time.monotonic()
    value = await bundle(tags, True)
    try:
        target, size = await asyncio.to_thread(build_file, value, format)
        original_size = size
        compressed = gzip_csv and format == 'complete'
        if compressed:
            target, size = await asyncio.to_thread(compress_csv, target)
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        logger.warning('Linked export preparation failed: format=%s error_type=%s', format, type(error).__name__)
        raise HTTPException(503, 'The export file could not be prepared. Saved results are unchanged.') from error
    logger.info('Linked export ready: format=%s results=%d executions=%d bytes=%d preparation_seconds=%.2f',
                format, len(value['results']), len(value['run_tags']), size, time.monotonic() - started)

    def chunks():
        try:
            while chunk := target.read(1024 * 1024):
                yield chunk
        finally:
            target.close()

    return StreamingResponse(chunks(), media_type='application/zip' if format == 'zip' else 'text/csv; charset=utf-8',
        headers={'Content-Length': str(size), 'Content-Disposition': 'attachment; filename="linked-results.zip"' if format == 'zip'
            else 'attachment; filename="complete-evidence.csv"', 'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no',
            'X-Memstara-Export-Results': str(len(value['results'])),
            'X-Memstara-Export-Executions': str(len(value['run_tags'])),
            'X-Memstara-Export-Warnings': str(len(value['warnings'])),
            # Fetch transparently decompresses gzip: the receipt must describe the
            # CSV delivered to JavaScript, while Content-Length describes the wire.
            'X-Memstara-Export-Bytes': str(original_size), 'Vary': 'Accept-Encoding',
            **({'Content-Encoding': 'gzip'} if compressed else {})}, background=BackgroundTask(target.close))
