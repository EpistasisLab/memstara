"""Task-scoped, server-validated Data Agent split plans for the web pipeline."""
import hashlib
import json
import math
import os
from pathlib import Path

VERSION = 'agent_stratified_allocation_v1'
SKILLS = {'data_training_heavy': (.1, .3), 'data_balanced_stratified': (.5, .5)}


def request(snapshot, trial):
    if (snapshot or {}).get('data_allocation_policy', {}).get('version') != VERSION:
        return None
    from memstara.combinations import task_books
    books = task_books(snapshot, trial).get('data', [])
    if len(books) != 1 or books[0] not in SKILLS:
        return None
    skill = books[0]
    low, high = SKILLS[skill]
    prompt = snapshot['prompts'][f'board/data:{skill}']
    return {'version': VERSION, 'skill': skill,
            'skill_prompt_sha256': hashlib.sha256(json.dumps(prompt, sort_keys=True).encode()).hexdigest(),
            'minimum_test_size': low, 'maximum_test_size': high, 'stratify': True,
            'population': 'exploration_rows_after_independent_validation_reserve',
            'balanced_meaning': 'equal_train_evaluation_sizes_not_class_resampling',
            'schema': {'test_size': 'number within skill bounds', 'seed': 'integer 0..2147483647',
                       'stratify': True},
            'instruction': 'Supply data_plan with these three fields in submit_result. '
                           'Preserve all rows and exact hypothesis predictors. The server performs the split.'}


def validate(value, specification, shared):
    if not isinstance(value, dict) or set(value) != {'test_size', 'seed', 'stratify'}:
        raise ValueError('Data skill requires data_plan with test_size, seed and stratify')
    fraction = value['test_size']
    if (type(fraction) not in (int, float) or not math.isfinite(fraction)
            or not specification['minimum_test_size'] <= fraction <= specification['maximum_test_size']):
        raise ValueError('Held-out fraction is outside the selected Data skill bounds')
    if value['stratify'] is not True:
        raise ValueError('Data skill requires stratify=true')
    if type(value['seed']) is not int or not 0 <= value['seed'] <= 2147483647:
        raise ValueError('Data split seed is outside the supported integer range')
    from memstara.evaluation import validate as validate_evaluation
    effective = validate_evaluation({**shared, 'test_size': fraction, 'seed': value['seed']})
    if effective['seed'] + effective['replicates'] - 1 > 2147483647:
        raise ValueError('Data seed plus replicate index exceeds the supported range')
    return effective


def partition_records(frame, target, effective, snapshot):
    from memstara.evaluation import evaluation_splits
    import numpy as np
    partition = snapshot.get('validation_partition')
    if not partition:
        raise ValueError('Data allocation requires the frozen independent validation reserve')
    rows = set(partition['exploration_rows'])
    reserved = sorted(set(range(len(frame))) - rows)
    def counts(indices):
        return {str(int(k)): int(v) for k, v in frame[target].iloc[indices].value_counts().items()}
    records = []
    for seed, train, test in evaluation_splits(frame[target], effective, partition=partition):
        if len(test) != math.ceil(len(rows) * effective['test_size']):
            raise ValueError('Too few exploration rows for the requested stratified allocation')
        records.append({'seed': seed, 'train_rows': train.tolist(), 'test_rows': test.tolist(),
                        'n_train': len(train), 'n_test': len(test),
                        'split_id': hashlib.sha256(test.tobytes()).hexdigest(),
                        'train_class_counts': counts(train), 'test_class_counts': counts(test)})
    return {'replicates': records, 'reserved_rows': reserved,
            'reserved_class_counts': counts(np.asarray(reserved, dtype=int)),
            'exploration_count': len(rows), 'reserved_count': len(reserved)}


def prepare(value, task, snapshot, subset):
    specification = request(snapshot, task['trial'])
    if not specification:
        if value is not None:
            raise ValueError('This Data skill does not accept a split plan')
        return None
    effective = validate(value, specification, snapshot['evaluation'])
    from memstara.evaluation import validate_clean_dataset
    import pandas as pd
    frame = validate_clean_dataset(Path(subset), task['y_column'], allow_missing=effective['engine'] == 'xgboost')
    config = os.environ.get('MEMSTARA_RUN_CONFIG')
    archived = Path(config).parent / 'feature_reproduction/input.csv' if config else None
    original = archived if archived and archived.is_file() else Path(os.environ['MEMSTARA_DATASET_PATH'])
    if hashlib.sha256(original.read_bytes()).hexdigest() != snapshot['dataset_sha256']:
        raise ValueError('Source dataset differs from the frozen run input')
    source = pd.read_csv(original)
    try:
        pd.testing.assert_frame_equal(frame, source[list(frame.columns)], check_dtype=False,
                                      check_exact=False, rtol=1e-12, atol=0)
    except (AssertionError, KeyError):
        raise ValueError('Extraction changed rows, values or row order; preserve the source dataset') from None
    return {'version': VERSION, 'request': specification, 'agent_plan': value,
            'effective_evaluation': effective, 'trial': task['trial'], 'task_id': task['task_id'],
            'run_tag': snapshot['run_tag'], 'config_hash': snapshot['config_hash'],
            'dataset_sha256': snapshot['dataset_sha256'],
            'subset_sha256': hashlib.sha256(Path(subset).read_bytes()).hexdigest(),
            **partition_records(frame, task['y_column'], effective, snapshot)}


def load_effective(path, snapshot, default):
    """ML uses only a verified server handoff, never ML-agent split overrides."""
    sidecar = Path(path).with_suffix('.comparison.json')
    if not sidecar.exists():
        if (snapshot or {}).get('data_allocation_policy'):
            raise ValueError('Data handoff is required before ML evaluation')
        return default, None
    context = json.loads(sidecar.read_text())
    record = context.get('data_allocation')
    required = request(snapshot, context.get('trial', 0))
    if required and not record:
        raise ValueError('Selected Data skill has no accepted split plan')
    if not record:
        return default, None
    if (record['request'] != required or record['config_hash'] != snapshot['config_hash']
            or record['subset_sha256'] != hashlib.sha256(Path(path).read_bytes()).hexdigest()):
        raise ValueError('Data allocation handoff differs from this task or run')
    effective = validate(record['agent_plan'], required, snapshot['evaluation'])
    from memstara.evaluation import validate_clean_dataset
    frame = validate_clean_dataset(Path(path), snapshot['y_column'], allow_missing=effective['engine'] == 'xgboost')
    rebuilt = partition_records(frame, snapshot['y_column'], effective, snapshot)
    if effective != record['effective_evaluation'] or any(record[k] != v for k, v in rebuilt.items()):
        raise ValueError('Saved Data allocation does not reproduce its recorded split')
    return effective, record
