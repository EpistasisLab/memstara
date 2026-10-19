"""Bound report inputs to one loop; retain full evidence outside model context."""
import hashlib
import json
from pathlib import Path

from memstara.pipeline.checkpoint import atomic_json


def project(row):
    """Explicit narrative projection, never raw evaluation arrays or nested artifacts."""
    keys = ('result_id', 'task_id', 'trial', 'question_id', 'model', 'auc',
            'y_column', 'columns_used', 'feature_importance', 'hypothesis', 'interpretation')
    result = {key: row.get(key) for key in keys}
    omitted = []
    for key in ('hypothesis', 'interpretation'):
        value = str(result.get(key) or '')
        if len(value) > 16000:
            omitted.append({'field': key, 'original_characters': len(value), 'included_characters': 16000})
        result[key] = value[:16000]
    evaluation = row.get('evaluation') or {}
    if isinstance(evaluation, str):
        evaluation = json.loads(evaluation)
    result['scalar_evaluation'] = {k: v for k, v in evaluation.items()
                                   if isinstance(v, (int, float, bool)) or v is None}
    result['evidence_scope'] = {
        'omitted_text': omitted,
        'excluded': ['raw evaluation arrays', 'serialized model artifacts', 'per-row predictions'],
        'full_result_id': row.get('result_id'),
        'instruction': 'Do not infer findings from excluded or omitted evidence.'}
    return result


async def execute(plan, loop, run_dir, args, kwargs, invoke, read):
    directory = Path(run_dir) / 'report_io'
    directory.mkdir(parents=True, exist_ok=True)
    trials = int(plan.get('trials', 1))
    query = {'run_tag': plan['run_tag']}
    if loop is not None:
        query.update(trial_start=(loop - 1) * trials, trial_end=loop * trials)
    data = await read(kwargs['registry'], 'read_results', query)
    if data.get('error') or not isinstance(data.get('results'), list):
        raise ValueError('Report evidence could not be read')
    rows = data['results']
    if loop is None:
        # Numbers are copied by code. No model rereads all detailed loop results.
        lines = ['# Recorded experiment results', '',
                 'Each row is one saved result. AUROC is exploratory, not independent validation.', '',
                 '| Trial (zero-based) | Result | Model | AUROC |', '|---|---|---|---|']
        for row in rows:
            lines.append(f"| {row['trial']} | {row['result_id']} | {row.get('model', '')} | {row.get('auc')} |")
        lines += ['', 'Per-loop explanations are stored in report_io/loop-*.json.',
                  'Earlier reports remain in the original checkpoint and trace. '
                  'Missing reports are not successful explanations.']
        validation = Path(run_dir) / 'final_validation.json'
        if validation.exists():
            lines += ['', '## Independent validation',
                      'Exact backend record; not used for tuning or candidate selection.',
                      '```json', validation.read_text(), '```']
        text = '\n'.join(lines)
        atomic_json(directory / 'comparison.json', {'run_tag': plan['run_tag'], 'results': [
            {k: r.get(k) for k in ('result_id', 'trial', 'model', 'auc')} for r in rows]})
        return text, {'status': 'completed', 'aggregation': 'deterministic comparison of saved results; no LLM call'}
    expected = range((loop - 1) * trials, loop * trials)
    if any(r['trial'] not in expected for r in rows):
        raise ValueError('Report tool returned evidence outside the current loop')
    records = [project(r) for r in rows]
    outputs = []
    entry = {}
    for row, record in zip(rows, records, strict=True):
        prompt = ('Write the explanation for this result only. This supplied evidence replaces the '
                  'general read_results instruction. Do not retrieve or summarize other loops. '
                  'Preserve measured numbers and limitations. Never invent missing evidence. '
                  'The full raw evaluation remains stored; excluded details are not evidence you have read.\n'
                  + json.dumps(record, ensure_ascii=False))
        # Explicit bytes budget bounds even highly token-dense Unicode before a paid call.
        if len(prompt.encode('utf-8')) > 120000:
            raise ValueError('Projected report evidence exceeds its input budget; no model request sent')
        receipt = {'loop': loop, 'run_tag': plan['run_tag'], 'result_id': record['result_id'],
                   'prompt': prompt, 'sha256': hashlib.sha256(prompt.encode()).hexdigest(),
                   'original_result_sha256': hashlib.sha256(
                       json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()}
        atomic_json(directory / f"loop-{loop}-result-{record['result_id']}-input.json", receipt)
        text, entry = await invoke(args[0], prompt, **{**kwargs, 'tools': []})
        atomic_json(directory / f"loop-{loop}-result-{record['result_id']}-output.json",
                    {'input_sha256': receipt['sha256'], 'output': text, 'execution': entry})
        if entry.get('status') != 'completed' or not text.strip():
            return text, entry
        outputs.append(text)
    if not records:
        return 'No completed result is available for this loop.', {'status': 'failed', 'error': 'Missing loop evidence'}
    text = '\n\n'.join(outputs)
    atomic_json(directory / f'loop-{loop}.json',
                {'loop': loop, 'text': text, 'result_ids': [r['result_id'] for r in records]})
    return text, entry
