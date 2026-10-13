"""Complete, isolated specialist experiment using the Memstara provider boundary.

Launch through pipeline.board --specialist-pilot-config FILE --run-dir DIR.
The explicit design is checked before any paid request. This mode uses local
experiment artifacts; it does not mutate the interactive workspace blackboard.
"""
from __future__ import annotations

import asyncio
from memstara.stage_models import for_stage
import csv
from datetime import UTC, datetime
import fcntl
import hashlib
import importlib.util
import importlib.metadata
import json
from pathlib import Path
import uuid

from memstara.control.catalog import resolve
from memstara.pilot_execution import schedule, feature_input, validate_hypothesis, validate_data_plan
from memstara.pilot_final import _save, invoke_model, run_final_stages, validate_config
from memstara.pilot_knowledge import retrieve, validate_binding
from memstara.pilot_ml import fit_pair, parameter_context, validate_ml_plan
from memstara.pipeline.prompts import load_prompt


def dataset_context(config):
    from memstara.evaluation import validate_clean_dataset
    frame = validate_clean_dataset(Path(config['dataset']), config['target'], allow_missing=True)
    # Paired LR evaluation requires complete predictors. This changes eligibility,
    # not patient rows or source values, and is disclosed in each hypothesis input.
    predictors = [c for c in frame if c != config['target'] and not frame[c].isna().any()]
    return predictors


def preflight(config: dict) -> tuple[list[dict], dict]:
    validate_config(config)
    rows = schedule(config)
    if type(config.get('seed')) is not int or not 0 <= config['seed'] <= 2147483647:
        raise ValueError('Provide an explicit nonnegative study seed')
    if not isinstance(config.get('run_id'), str) or not config['run_id'].strip():
        raise ValueError('Provide a nonempty study run_id')
    dataset = Path(config['dataset'])
    with dataset.open(newline='', encoding='utf-8-sig') as stream:
        header = next(csv.reader(stream))
    if config['target'] not in header or len(header) != len(set(header)):
        raise ValueError('Dataset requires unique headers and the configured target')
    feature_input(dataset_context(config), seed=config['seed'], random_selection=False)
    if not isinstance(config.get('outcome_description'), str) or not config['outcome_description'].strip():
        raise ValueError('Provide the clinical outcome description for question generation')
    skills = {}
    for stage, ids in config['choices'].items():
        for skill_id in ids:
            item = resolve(skill_id)
            if not item or item['stage'] != stage:
                raise ValueError(f'{skill_id}: not an available {stage} skill')
            skills[skill_id] = item
    if not set(config['choices']['data']) <= {'data_training_heavy', 'data_balanced_stratified'}:
        raise ValueError('Select the training-heavy and/or balanced-stratified data skills')
    if not set(config['choices']['ml']) <= {
            'ml_logistic_regression', 'ml_xgboost', 'ml_pilot_lr_focus', 'ml_pilot_xgb_focus'}:
        raise ValueError('Select the paired-model ML skills; legacy fixed-policy skills are incompatible')
    if not set(config['choices']['interpreter']) <= {'shared-anil-shap', 'shared-anil-lime'}:
        raise ValueError('This pilot requires the current Anil interpretation skills')
    if not set(config['choices']['report']) <= {'shared-anil-addiction', 'shared-anil-hiv'}:
        raise ValueError('This pilot requires the current Anil explanation skills')
    for name in config['choices']['hypothesis']:
        if name != 'random_features':
            validate_binding(config.get('hypothesis_knowledge', {}).get(name))
    for module in ('shap', 'lime', 'xgboost'):
        if importlib.util.find_spec(module) is None:
            raise ValueError(f'Missing numerical dependency: {module}; install the pilot extra')
    return rows, skills


def paused(output: Path) -> None:
    if (output / 'pause.request').exists():
        raise RuntimeError('Study paused by request; no subsequent stage was started')


def comparison(output: Path, completed: list[dict]) -> None:
    _save(output / 'comparison.json', {'completed_combinations': completed})
    with (output / 'comparison.csv').open('w', newline='') as stream:
        fields = ['combination', 'hypothesis_skill', 'data_skill', 'ml_skill', 'interpretation_skill',
                  'explanation_skill', 'question', 'features', 'model', 'auroc', 'average_precision',
                  'brier', 'f1', 'tn', 'fp', 'fn', 'tp', 'interpretation_file', 'explanation_file']
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in completed:
            for model, metrics in item['metrics'].items():
                writer.writerow({'combination': item['scope']['combination_id'],
                    **{f'{label}_skill': item['condition'][stage] for label, stage in
                       (('hypothesis', 'hypothesis'), ('data', 'data'), ('ml', 'ml'),
                        ('interpretation', 'interpreter'), ('explanation', 'report'))},
                    'question': item['question'], 'features': json.dumps(item['features']), 'model': model,
                    **{name: metrics.get(name) for name in
                       ('auroc', 'average_precision', 'brier', 'f1', 'tn', 'fp', 'fn', 'tp')},
                    'interpretation_file': item['interpretation'], 'explanation_file': item['explanation']})


async def json_stage(stage, system, payload, profile, directory, invoke, *, resume, check_pause):
    """Persist each attempt; completed stages are not paid for again on explicit resume."""
    result_path = directory / f'{stage}.result.json'
    request = {'system': system, 'payload': payload, 'model': profile}
    input_path = directory / f'{stage}.request.json'
    if resume and result_path.exists():
        if json.loads(input_path.read_text()) != request:
            raise ValueError('Completed stage has a different request; resume is unsafe')
        return json.loads(result_path.read_text())
    _save(input_path, request)
    check_pause()
    response = await invoke(profile, system, payload)
    _save(directory / f'{stage}.response.json', response)
    text = response.get('text', '').strip()
    if text.startswith('```'):
        lines = text.splitlines()
        if lines[-1].strip() != '```':
            raise ValueError('Unterminated JSON code block')
        text = '\n'.join(lines[1:-1])
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError('Agent must return a JSON object')
    # The caller validates semantics before marking this stage reusable.
    return value


async def run_study(config: dict, output: Path, *, resume=False, invoke=invoke_model,
                    knowledge=retrieve, fit=fit_pair) -> dict:
    rows, skills = preflight(config)
    if invoke is invoke_model:
        from memstara.stage_models import preflight_profiles
        await preflight_profiles(config["models"])
    dataset = Path(config['dataset'])
    predictors = dataset_context(config)
    code_paths = [Path(__file__), *[Path(__file__).parents[1] / name for name in
                  ('pilot_ml.py', 'pilot_final.py', 'pilot_execution.py', 'pilot_handoffs.py',
                   'pilot_knowledge.py', 'pilot_models.py', 'stage_models.py')]]
    prompts = {stage: load_prompt(f'pilot/{stage}') for stage in ('hypothesis', 'data', 'ml')}
    manifest = {'config': config, 'schedule': rows, 'dataset_sha256': hashlib.sha256(dataset.read_bytes()).hexdigest(),
                'skills': {name: {'hash': item['hash'], 'content': item['content']} for name, item in skills.items()},
                'code_hashes': {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in code_paths},
                'packages': {name: importlib.metadata.version(name) for name in
                             ('numpy', 'pandas', 'scikit-learn', 'xgboost', 'shap', 'lime')},
                'prompts': prompts}
    output.mkdir(parents=True, exist_ok=resume)
    with (output / 'execution.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest_path = output / 'manifest.json'
        if resume:
            if not manifest_path.exists() or json.loads(manifest_path.read_text()) != manifest:
                raise ValueError('Resume requires identical dataset, code, skills, prompts and configuration')
        else:
            _save(manifest_path, manifest)
        completed = []
        current_stage = 'preparation'
        current_loop = None
        try:
            for condition in rows:
                current_loop = condition['combination_id']
                directory = output / f'combination-{current_loop:03d}'
                directory.mkdir(exist_ok=resume)
                paused(output)
                marker = directory / 'completed.json'
                if resume and marker.exists():
                    saved = json.loads(marker.read_text())
                    if saved['condition'] != condition or saved['scope']['run_id'] != config['run_id']:
                        raise ValueError('Completed combination identity differs from the frozen schedule')
                    for filename, digest in saved['artifact_hashes'].items():
                        path = directory / filename
                        if not path.resolve().is_relative_to(directory.resolve()) or not path.is_file():
                            raise ValueError('A completed combination artifact is missing')
                        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                            raise ValueError('A completed combination artifact changed')
                    completed.append(saved)
                    comparison(output, completed)
                    continue
                scope = {'run_id': config['run_id'], 'combination_id': current_loop,
                         'question_id': f"{config['run_id']}:{current_loop}"}
                def progress(stage, current_loop=current_loop):
                    nonlocal current_stage
                    paused(output)
                    if hashlib.sha256(dataset.read_bytes()).hexdigest() != manifest['dataset_sha256']:
                        raise ValueError('Dataset changed after study preparation; stop before the next stage')
                    current_stage = stage
                    _save(output / 'status.json', {'status': 'running', 'combination': current_loop,
                          'stage': stage, 'completed_combinations': len(completed), 'total': len(rows)})
                    with (output / 'events.jsonl').open('a') as events:
                        events.write(json.dumps({'at': datetime.now(UTC).isoformat(), 'stage': stage,
                                                 'combination': current_loop}) + '\n')
                async def call(stage, payload, validate, condition=condition, directory=directory, progress=progress):
                    progress(stage)
                    system = (prompts[stage]['system_prompt'] + '\n\nSelected skill:\n' +
                              skills[condition[stage]]['content'])
                    # Invalid JSON or semantic output pauses the study; it never silently advances.
                    result = await json_stage(stage, system, payload, for_stage(config['models'], stage), directory,
                                              invoke, resume=resume, check_pause=lambda: paused(output))
                    result = validate(result)
                    _save(directory / f'{stage}.result.json', result)
                    return result
                context = feature_input(predictors, seed=(config['seed'] + current_loop) % 2147483648,
                                        random_selection=condition['hypothesis'] == 'random_features')
                evidence_path = directory / 'hypothesis.evidence.json'
                progress('hypothesis_knowledge')
                if resume and evidence_path.exists():
                    evidence = json.loads(evidence_path.read_text())
                elif context['required_features'] is None:
                    binding = config['hypothesis_knowledge'][condition['hypothesis']]
                    evidence = await knowledge(binding, skills[condition['hypothesis']]['title'])
                    if evidence.get('database_id') != binding['database_id'] or not evidence.get('documents'):
                        raise ValueError('Guided hypothesis requires evidence from its configured knowledge store')
                    _save(evidence_path, evidence)
                else:
                    evidence = {'documents': [], 'selection': 'random baseline; no knowledge retrieval'}
                    _save(evidence_path, evidence)
                def check_hypothesis(value, context=context, evidence=evidence):
                    validate_hypothesis(value, context)
                    ids = value.get('evidence_ids')
                    known = {doc['id'] for doc in evidence['documents']}
                    if not isinstance(ids, list) or not set(ids) <= known or (known and not ids):
                        raise ValueError('Hypothesis evidence IDs must refer to the supplied documents')
                    return value
                hypothesis = await call('hypothesis', {
                    **context, 'knowledge_evidence': evidence, 'outcome': config['outcome_description'],
                    'eligibility': 'Non-target columns with no missing values; source rows are unchanged'},
                    check_hypothesis)
                data_plan = await call('data', {'hypothesis': hypothesis, 'schema': {
                    'test_size': 'fraction', 'seed': 'integer', 'stratify': True}},
                    lambda value, skill=condition['data']: validate_data_plan(value, skill))
                ml_plan = await call('ml', {'hypothesis': hypothesis, 'data_plan': data_plan,
                                           'parameter_defaults': parameter_context()}, validate_ml_plan)
                progress('paired_ml_and_xai')
                paired_path = directory / 'ml' / 'paired-results.json'
                if resume and paired_path.exists():
                    bundle = json.loads(paired_path.read_text())
                    if bundle['scope'] != scope:
                        raise ValueError('Paired ML result belongs to another experiment')
                    paired = bundle['results']
                else:
                    ml_output = directory / 'ml'
                    if ml_output.exists():
                        # Preserve every failed attempt; retries never overwrite numerical artifacts.
                        ml_output.rename(directory / f'ml-incomplete-{uuid.uuid4().hex}')
                    paired = await asyncio.to_thread(fit, dataset, config['target'], hypothesis['features'],
                                                    data_plan, ml_plan, scope, ml_output)
                progress('interpretation_and_explanation')
                async def final_invoke(profile, system, payload, progress=progress):
                    progress('explanation' if payload.get('expert') else 'interpretation')
                    return await invoke(profile, system, payload)
                method = condition['interpreter'].removeprefix('shared-anil-')
                expert = condition['report'].removeprefix('shared-anil-')
                await run_final_stages(config, {'scope': scope, 'results': paired, 'hypothesis': hypothesis},
                                       directory / 'final',
                                       invoke=final_invoke, knowledge=knowledge, methods=(method,), experts=(expert,),
                                       resume=resume)
                item = {'scope': scope, 'condition': condition, 'question': hypothesis['question'],
                        'hypothesis': hypothesis['hypothesis'], 'features': hypothesis['features'],
                        'metrics': {row['model']: row['metrics'] for row in paired},
                        'interpretation': f'combination-{current_loop:03d}/final/{method}.md',
                        'explanation': f'combination-{current_loop:03d}/final/{expert}.md'}
                item['artifact_hashes'] = {
                    str(path.relative_to(directory)): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in sorted(directory.rglob('*')) if path.is_file()}

                _save(marker, item)
                completed.append(item)
                comparison(output, completed)
            status = {'status': 'completed', 'completed_combinations': len(completed), 'total': len(rows)}
            _save(output / 'status.json', status)
            return status
        except BaseException as exc:
            _save(output / 'status.json', {'status': 'paused', 'combination': current_loop,
                  'stage': current_stage, 'completed_combinations': len(completed), 'total': len(rows),
                  'error_type': type(exc).__name__, 'automatic_continuation': False})
            raise
