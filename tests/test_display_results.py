import asyncio
import copy
import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'viewer/api'))
import display_results
import scene


def evidence():
    metrics = {'auroc': .8123456789, 'f1': .73}
    matrix = {'tn': 350, 'fp': 40, 'fn': 12, 'tp': 25, 'rows': 'actual', 'columns': 'predicted', 'labels': [0, 1]}
    fit = {'seed': 42, 'n_train': 1280, 'n_test': 427, 'parameters': {'C': .37},
           'performance': {'test': {'n': 427, 'threshold': .5, 'metrics': metrics, 'confusion_matrix': matrix}},
           'operating_point': {'probability_cutoff': .5}, 'predictions': [0.123456789] * 5000}
    evaluation = {'model': 'lr', 'seed': 42, 'skills': {'hypothesis': ['hiv-no-knowledge']},
                  'interpretations': [{'status': 'done', 'text': 'Unchanged Interpretation'}],
                  'evaluation': {'replicates': [fit, {**fit, 'seed': 43}]},
                  'comparison': {'variants': [{'id': 'full', 'auc': .8123456789, 'evaluation': {'replicates': [fit]}}]},
                  'data_allocation': {'replicates': [{'seed': 42, 'n_train': 1280, 'n_test': 427, 'train_indices': list(range(1280))}]}}
    evaluation['model_results'] = {'lr': {'model': 'lr', 'evaluation': evaluation['evaluation']}}
    return {'result_id': 1, 'task_id': 2, 'run_tag': 'original', 'trial': 0, 'iteration': 1,
            'interpretation': 'Original text', 'evaluation': evaluation}


def test_large_display_preserves_every_result_fit_metric_and_source():
    row = evidence()
    original = copy.deepcopy(row)
    rows = [{**row, 'result_id': n, 'iteration': n + 1} for n in range(1200)]
    projected = display_results.results(rows)
    assert len(projected) == 1200
    assert [r['result_id'] for r in projected] == list(range(1200))
    assert row == original
    for result in projected:
        measured = result['evaluation']
        for i, fit in enumerate(measured['evaluation']['replicates']):
            raw = row['evaluation']['evaluation']['replicates'][i]
            assert fit['performance'] == raw['performance']
            assert fit['parameters'] == raw['parameters']
            assert fit['seed'] == raw['seed']
            assert 'predictions' not in fit
        assert measured['model_results']['lr']['evaluation'] == measured['evaluation']
        assert measured['interpretations'] == row['evaluation']['interpretations']
        assert result['interpretation'] == row['interpretation']
    assert len(json.dumps(projected)) < len(json.dumps(rows)) / 10


def test_display_does_not_mutate_complete_detail_or_export_records(monkeypatch):
    row = evidence()
    fetch = AsyncMock(return_value=[row])
    monkeypatch.setattr(scene, '_results', fetch)
    shown = asyncio.run(scene._display_results('original'))
    full = asyncio.run(scene._results('original'))
    assert len(full[0]['evaluation']['evaluation']['replicates'][0]['predictions']) == 5000
    assert 'predictions' not in shown[0]['evaluation']['evaluation']['replicates'][0]
