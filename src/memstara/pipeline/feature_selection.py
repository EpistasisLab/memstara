"""Frozen original-column selection policy for web All Combinations runs."""
import hashlib
import json
import random

VERSION = 'original_predictors_4_20_v1'


def freeze(plan):
    """Use the frozen eligible catalog; never inspect outcomes or model scores."""
    columns = [r['column'] for r in plan['feature_context']['features']]
    if (len(columns) < 4 or len(set(columns)) != len(columns)
            or plan['y_column'] in columns):
        raise ValueError('All Combinations requires at least four distinct eligible predictors')
    # Separate baseline additions would invalidate the sampled condition and its size.
    if plan.get('comparison_policy', {}).get('baseline_columns'):
        raise ValueError('4–20 feature selection requires an empty fixed baseline; no predictors may be added')
    return {'version': VERSION, 'minimum': 4, 'maximum': 20,
            'seed': plan['evaluation']['seed'], 'eligible_features': columns,
            'pool_sha256': hashlib.sha256(json.dumps(columns, ensure_ascii=False).encode()).hexdigest(),
            'pool_source': ('frozen_complete_predictor_catalog'
                            if plan['feature_context'].get('eligibility') else 'frozen_header_catalog'),
            **({'eligibility': plan['feature_context']['eligibility']}
               if plan['feature_context'].get('eligibility') else {}),
            'dataset_sha256': plan['dataset_sha256']}


def context(plan, wave):
    policy = (plan or {}).get('feature_selection_policy')
    if not policy:
        return None
    if policy.get('version') != VERSION:
        raise ValueError('Unsupported feature selection policy')
    if type(wave) is not int or wave < 0:
        raise ValueError('Feature selection requires a nonnegative Loop index')
    from memstara.combinations import loop_flavors
    flavors = loop_flavors(plan['combination_plan'], wave + 1)
    skill = next(a['id'] for a in flavors['agents'] if a['stage'] == 'hypothesis')
    mode = 'all' if skill == 'heart-failure-all' else 'random' if skill == 'random_features' else 'guided'
    # Seed derivation is independent of process hash randomization and retries.
    seed = int.from_bytes(hashlib.sha256(f"{policy['seed']}:{wave}".encode()).digest()[:4], 'big')
    pool = policy['eligible_features']
    rng = random.Random(seed)
    count = plan.get('controlled_comparison', {}).get('feature_count')
    required = list(pool) if mode == 'all' else None
    if mode == 'all':
        count = len(pool)
    if mode == 'random':
        required = rng.sample(pool, count if count is not None else rng.randint(4, min(20, len(pool))))
    sampling = 'fixed_count_without_replacement' if count else 'uniform_count_then_without_replacement'
    return {'version': VERSION, 'mode': mode, 'minimum': count or 4, 'maximum': count or 20,
            'seed': seed if mode == 'random' else None, 'required_features': required,
            'sampling': sampling if mode == 'random' else 'all_eligible' if mode == 'all' else 'llm',
            'pool_sha256': policy['pool_sha256'], 'pool_size': len(pool),
            'pool_source': policy['pool_source'], 'dataset_sha256': policy['dataset_sha256'],
            'run_tag': plan['run_tag'], 'pipeline_id': plan.get('pipeline_id', ''),
            'loop': wave + 1, 'combination': flavors['combination'], 'skill': skill}


def scoped(plan, wave):
    selected = context(plan, wave)
    if not selected or selected['mode'] != 'random':
        return plan
    return {**plan, 'knowledge_policy': {'mode': 'no_okf', 'retrieval_enabled': False},
            'hypothesis_policy': {**plan.get('hypothesis_policy', {}),
                                  'version': 'random_feature_control_v1', 'prior_ml_feedback': False}}


def validate(columns, plan, trial):
    selected = context(plan, trial)
    if selected is None:
        return None
    if (not isinstance(columns, list) or any(not isinstance(c, str) for c in columns)
            or (selected['mode'] != 'all' and not 4 <= len(columns) <= 20) or len(set(columns)) != len(columns)):
        raise ValueError('Select 4–20 distinct original predictor columns')
    if plan['y_column'] in columns or set(columns) - set(plan['feature_selection_policy']['eligible_features']):
        raise ValueError('Predictors must belong to the frozen eligible pool and exclude the target')
    if not selected['minimum'] <= len(columns) <= selected['maximum']:
        raise ValueError('Use the exact feature count frozen for this controlled comparison')
    if selected['mode'] in ('random', 'all') and columns != selected['required_features']:
        raise ValueError('Use exactly the server-sampled random predictors in their recorded order')
    return {**selected, 'actual_count': len(columns), 'features': list(columns)}


def instructions(plan, wave):
    selected = context(plan, wave)
    if selected is None:
        return ''
    if selected['mode'] == 'all':
        return '\nFEATURE SELECTION INPUT: ' + json.dumps(selected, ensure_ascii=False) + '\nUse exactly required_features in the recorded order; do not sample or select a subset.'
    message = ('\nFEATURE SELECTION INPUT: ' + json.dumps(selected, ensure_ascii=False)
               + '\nSelect 4–20 distinct original columns (before encoding), excluding the outcome. '
                 'create_task enforces the range and pool. Do not add baseline predictors. ')
    if selected['mode'] == 'random':
        message += ('This is a random-feature control, not knowledge-grounded selection. '
                    'Use required_features exactly, including order, as predictor_concepts in propose_questions '
                    'and columns in create_task. Explain their label-derived meanings and the proposed joint '
                    'prediction, without claiming evidence of association. Supply source_ids=[], okf_tags=[], '
                    'okf_concept_ids=[]; map each exact column name to itself with source_id="". '
                    'Do not call knowledge or matcher tools, change the sample, or use feedback to select features. '
                    'These instructions override ordinary knowledge-grounding and clinical-concept instructions. ')
    if selected['minimum'] == selected['maximum']:
        message += f"This matched comparison REQUIRES EXACTLY {selected['minimum']} original predictor columns. "
    return message


def hypothesis_tools(tools, plan, wave):
    """Only the random condition removes knowledge retrieval and semantic remapping."""
    selected = context(plan, wave)
    if not selected or selected['mode'] != 'random':
        return tools
    from memstara.pipeline.ablation import filter_tools
    return [t for t in filter_tools(tools, scoped(plan, wave))
            if (t.get('tool_name') or t.get('name')) not in ('match_concept', 'match_concepts')]


def validate_measured(features, selection):
    """A result describes the original predictors actually fitted, never an agent claim."""
    if (not isinstance(features, list) or any(not isinstance(c, str) for c in features)
            or len(features) != len(selection['features'])
            or set(features) != set(selection['features'])):
        raise ValueError('Measured predictors differ from the frozen hypothesis selection')
    return features
