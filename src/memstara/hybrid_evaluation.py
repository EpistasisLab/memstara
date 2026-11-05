"""Training-CV selection of a frozen baseline or its graph augmentation.

The two candidates share outer/inner split seeds and fixed ML settings. Test
metrics are recorded for comparison, never read by the selection function.
"""
import copy
import hashlib
import json
import math
from pathlib import Path

from memstara.pipeline.hybrid import VERSION


def choose(candidates):
    if not candidates or candidates[0]['id'] != 'baseline' or len(candidates) > 2:
        raise ValueError('Hybrid requires a baseline and at most one augmentation candidate')
    scores = {}
    for candidate in candidates:
        values = candidate['training_cv_auroc']
        if len(values) != 1 or any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in values):
            raise ValueError('Hybrid requires one finite training-CV AUROC per candidate')
        if candidate['id'] not in ('baseline', 'expanded') or candidate['id'] in scores:
            raise ValueError('Invalid hybrid candidate identity')
        scores[candidate['id']] = sum(values) / len(values)
    return 'expanded' if scores.get('expanded', -1) > scores['baseline'] + 1e-12 else 'baseline'


def validate_receipt(features, frozen, proposed, receipt):
    if (not isinstance(receipt, dict) or receipt.get('version') != VERSION
            or receipt.get('baseline_sha256') != frozen['baseline_sha256']
            or receipt.get('baseline_columns') != frozen['baseline_columns']
            or receipt.get('expanded_columns') != proposed):
        raise ValueError('Measured hybrid selection differs from the frozen candidate')
    selected = choose(receipt['candidates'])
    expected_candidates = [('baseline', frozen['baseline_columns'])]
    if proposed != frozen['baseline_columns']:
        expected_candidates.append(('expanded', proposed))
    if [(c['id'], c['features']) for c in receipt['candidates']] != expected_candidates:
        raise ValueError('Hybrid candidate features differ from their frozen identities')
    if receipt.get('selected_candidate') != selected:
        raise ValueError('Hybrid selection did not follow training CV')
    expected = frozen['baseline_columns'] if selected == 'baseline' else proposed
    if features != expected:
        raise ValueError('Fitted predictors differ from the selected hybrid candidate')
    return features


def score_hybrid(path, target, plan, snapshot, *, configuration=None, xai_request=None):
    from memstara.evaluation import score

    context = json.loads(path.with_suffix('.comparison.json').read_text())
    frozen = context['hybrid']
    from memstara.pipeline.hybrid import require

    require(snapshot, context['trial'])
    if (frozen.get('version') != VERSION or context.get('config_hash') != snapshot['config_hash']
            or context.get('target') != target or context.get('baseline_columns') != []
            or context.get('dataset_sha256') != hashlib.sha256(path.read_bytes()).hexdigest()):
        raise ValueError('Hybrid comparison context changed')
    if plan['replicates'] != 1 or plan['folds'] < 2 or plan['search_trials'] != 1 or not configuration:
        raise ValueError('Hybrid requires one split, at least two training CV folds and fixed model settings')
    full = context['hypothesis_columns']
    baseline = frozen['baseline_columns']
    if full != baseline + frozen['augmentation_columns'] or not baseline:
        raise ValueError('Hybrid must preserve baseline order and separately recorded additions')
    candidates, measured = [], {}
    variants = [('baseline', baseline)] + ([('expanded', full)] if full != baseline else [])
    for name, columns in variants:
        result = score(path, target, plan, predictors=columns, configuration=configuration,
                       explain=False, persist=False)
        runs = result['evaluation']['replicates']
        signature = [(r['seed'], r['train_split_id'], r['split_id']) for r in runs]
        if measured:
            previous = measured['baseline']['evaluation']['replicates']
            if signature != [(r['seed'], r['train_split_id'], r['split_id']) for r in previous]:
                raise ValueError('Hybrid candidates must use identical training and held-out rows')
        if any(r.get('cv_folds', 0) < 2 for r in runs):
            raise ValueError('Hybrid training CV was not performed')
        candidates.append({'id': name, 'features': columns,
                           'training_cv_auroc': [r.get('cv_auc') for r in runs]})
        measured[name] = result
    selected = choose(candidates)
    chosen = measured[selected]
    result = score(path, target, plan, predictors=chosen['features'], configuration=configuration,
                   xai_request=xai_request)
    if ([r['prediction_sha256'] for r in result['evaluation']['replicates']]
            != [r['prediction_sha256'] for r in chosen['evaluation']['replicates']]):
        raise ValueError('Selected hybrid refit did not reproduce candidate predictions')
    receipt = {'version': VERSION, 'baseline_sha256': frozen['baseline_sha256'],
               'baseline_columns': baseline, 'expanded_columns': full, 'candidates': candidates,
               'selection_metric': 'mean_training_cv_auroc', 'selected_candidate': selected,
               'tie_policy': 'baseline within absolute tolerance 1e-12',
               'selection_scope': 'Training CV only; held-out metrics never determine promotion',
               'validation_status': 'exploratory_not_independently_validated'}
    validate_receipt(result['features'], frozen, full, receipt)
    result['hybrid_selection'] = receipt
    base_auc = measured['baseline']['auc']
    result['comparison'] = {
        'version': 'paired_groups_v1', 'method': VERSION, 'status': 'completed',
        'baseline_configured': True, 'baseline_source': 'isolated_model_knowledge',
        'baseline_columns': baseline, 'groups': context['groups'],
        'variants': [{'id': name, 'label': 'Frozen model-knowledge baseline' if name == 'baseline'
                       else 'Baseline + graph augmentation', 'features': columns, 'status': 'completed',
                      'auc': measured[name]['auc'], 'replicates': measured[name]['evaluation']['replicates'],
                      'delta_from_baseline': measured[name]['auc'] - base_auc,
                      'paired_deltas': [r['auc'] - b['auc'] for r, b in zip(
                          measured[name]['evaluation']['replicates'], measured['baseline']['evaluation']['replicates'], strict=True)]}
                     for name, columns in variants],
        'selected_candidate': selected, 'parameters_policy': 'Identical agent-frozen settings and training-CV folds',
        'scope': 'Exploratory paired comparison; held-out gain is not guaranteed by training selection',
        'timing_status': snapshot['comparison_policy'].get('timing_status', 'unverified'),
        'interpretation_limit': snapshot['comparison_policy'].get('interpretation_limit'),
        'feature_count_control': 'Not included; an incremental gain is not proof of graph-specific superiority',
    }
    # Preserve the selection decision alongside the selected fitted model bundle.
    reproducibility = result['evaluation'].get('reproducibility')
    if reproducibility:
        bundle = Path(reproducibility['bundle_path'])
        decision = bundle / 'hybrid-selection.json'
        decision.write_text(json.dumps({'frozen_candidate': frozen, 'selection': receipt}, indent=2))
        decision.chmod(0o600)
        manifest_path = bundle / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['files'][decision.name] = hashlib.sha256(decision.read_bytes()).hexdigest()
        source = Path(__file__)
        saved_source = bundle / source.name
        saved_source.write_bytes(source.read_bytes())
        saved_source.chmod(0o600)
        manifest['code'][source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest['files'][source.name] = manifest['code'][source.name]
        saved_result = bundle / 'result.json'
        archived_result = copy.deepcopy(result)
        archived_result['evaluation'].pop('reproducibility', None)
        saved_result.write_text(json.dumps(archived_result, indent=2, allow_nan=False))
        manifest['files'][saved_result.name] = hashlib.sha256(saved_result.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False))
        reproducibility['manifest_sha256'] = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    return result
