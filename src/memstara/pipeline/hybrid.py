"""Opt-in, durable model-knowledge baseline followed by graph augmentation.

Only the new skill enables this protocol. No state or source policy of an existing
condition is changed. Baseline calls have a separate prompt and a metadata-only
tool allowlist; accepted baselines are immutable across retries.
"""
import copy
from contextvars import ContextVar
import hashlib
import json
import os
from pathlib import Path

SKILL = 'hiv-model-knowledge-with-graph-augmentation'
VERSION = 'model_knowledge_graph_augmentation_v1'
BASE_CALL = ContextVar('memstara_hybrid_baseline_call', default=False)
BASE_TOOLS = frozenset({'lookup_predictor_catalog', 'freeze_hybrid_candidate'})


def selected(plan, wave):
    if not plan:
        return False
    if plan.get('combination_plan'):
        from memstara.combinations import loop_flavors
        names = [a['id'] for a in loop_flavors(plan['combination_plan'], wave + 1)['agents']
                 if a['stage'] == 'hypothesis']
    else:
        names = plan.get('books', {}).get('hypothesis', [])
    if SKILL in names and names != [SKILL]:
        raise ValueError('The hybrid skill requires its own scheduled condition')
    return names == [SKILL]


def require(plan, wave):
    if not selected(plan, wave) or plan.get('hybrid_policy', {}).get('version') != VERSION:
        raise ValueError('This execution has no frozen hybrid protocol; start a new hybrid condition')


def freeze_policy(state, previous=None):
    if SKILL not in state.get('books', {}).get('hypothesis', []):
        return
    if previous is not None:
        if previous.get('hybrid_policy', {}).get('version') != VERSION:
            raise ValueError('Historical hybrid execution has no verified protocol')
        state['hybrid_policy'] = copy.deepcopy(previous['hybrid_policy'])
        return
    if (not state.get('combination_plan') or state['trials'] != 1 or state['hypotheses'] != 1
            or state['evaluation']['replicates'] != 1):
        raise ValueError('Hybrid requires All Combinations, one hypothesis and one held-out split per Loop')
    if (state.get('knowledge_mode') != 'okf' or state.get('controlled_comparison')
            or state['comparison_policy']['baseline_columns']):
        raise ValueError('Hybrid requires selected OKF sources and no separate baseline/controlled protocol')
    if state.get('ml_overrides', {}).get('folds') == 0:
        raise ValueError('Hybrid requires training CV; remove the zero-fold override or select 2–5 folds')
    from memstara.pipeline.prompts import load_prompt
    prompt = load_prompt('board/hypothesis', 'hiv-no-knowledge')
    # A dedicated agent never receives the graph workflow or graph corpus metadata.
    prompt['system_prompt'] = prompt['system_prompt'].replace('propose_questions', 'freeze_hybrid_candidate')
    state['hybrid_policy'] = {
        'version': VERSION, 'selection_metric': 'mean_training_cv_auroc',
        'selection_rule': 'strict_improvement_else_baseline', 'minimum_cv_folds': 2,
        'baseline_prompt': prompt, 'baseline_tools': sorted(BASE_TOOLS),
        'scope': 'Exploratory paired comparison; no guaranteed improvement on unseen subjects',
    }


def baseline_scope(plan):
    profile = (plan or {}).get('research_profile') or {}
    config = profile.get('configuration', {})
    return {**plan, 'no_knowledge_condition': True,
            'knowledge_policy': {'mode': 'no_okf', 'retrieval_enabled': False},
            'knowledge_mode': 'llm_only', 'knowledge_hashes': {}, 'knowledge_path': '',
            'research_profile': {'configuration': {**config, 'knowledge_mode': 'llm_only',
                                                   'knowledge_path': ''}} if profile else None}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def state_path(plan, wave):
    require(plan, wave)
    config = os.environ.get('MEMSTARA_RUN_CONFIG')
    if not config:
        raise ValueError('Hybrid requires the frozen execution configuration')
    root = Path(config).resolve().parent
    return root / f'hybrid_baseline_{wave}.json'


def read_baseline(plan, wave, *, required=True):
    path = state_path(plan, wave)
    if not path.exists() and not required:
        return None
    if path.is_symlink():
        raise ValueError('Hybrid baseline cannot be a symlink')
    record = json.loads(path.read_text())
    expected = {'run_tag': plan['run_tag'], 'config_hash': plan['config_hash'],
                'wave': wave, 'version': VERSION}
    if any(record.get(k) != v for k, v in expected.items()):
        raise ValueError('Hybrid baseline belongs to another execution')
    if record.get('sha256') != digest({k: v for k, v in record.items() if k != 'sha256'}):
        raise ValueError('Hybrid baseline checksum changed')
    return record


def save_baseline(plan, wave, proposal):
    require(plan, wave)
    if type(wave) is not int or wave < 0:
        raise ValueError('Hybrid wave must be a nonnegative integer')
    from memstara.pipeline.question_contract import make_contract
    from memstara.pipeline.feature_selection import validate
    contract = make_contract({**proposal, 'origin_wave': wave}, baseline_scope(plan))
    columns = [r['column'] for r in contract['proposed_mapping']]
    validate(columns, plan, wave)
    record = {'version': VERSION, 'run_tag': plan['run_tag'], 'config_hash': plan['config_hash'],
              'wave': wave, 'contract': contract, 'columns': columns,
              'provenance': 'isolated_model_knowledge'}
    record['sha256'] = digest(record)
    path = state_path(plan, wave)
    if path.exists():
        if read_baseline(plan, wave) != record:
            raise ValueError('Accepted hybrid baseline is immutable; reuse it unchanged')
        return record
    # The execution owner serializes writers; exclusive creation also prevents a
    # concurrent tool call from replacing an already accepted candidate.
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        json.dump(record, stream, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    return record


def contract_metadata(plan, wave, mapping):
    record = read_baseline(plan, wave)
    original = record['contract']['proposed_mapping']
    if not isinstance(mapping, list) or mapping[:len(original)] != original:
        raise ValueError('Keep every frozen baseline mapping first, exactly unchanged')
    additions = mapping[len(original):]
    if any(r.get('column') in record['columns'] or not r.get('source_id') for r in additions):
        raise ValueError('Only additional, source-grounded columns may augment the baseline')
    return {'version': VERSION, 'baseline_sha256': record['sha256'],
            'baseline_columns': record['columns'], 'baseline_mapping': original,
            'augmentation_columns': [r['column'] for r in additions]}


def instructions(plan, wave):
    record = read_baseline(plan, wave)
    return ('\nHYBRID EXECUTION: ' + json.dumps(record, ensure_ascii=False) +
            '\nThe driver froze this model-knowledge candidate before graph exposure. '
            'Keep its predictor concepts and proposed_mapping unchanged and first. '
            'Search the selected whole OKF for a coherent, nonredundant augmentation. '
            'Use source_id="" only for frozen baseline mappings; every additional mapping '
            'needs a document actually read. Include only additional source IDs in source_ids. '
            'If no defensible augmentation is available, propose the baseline unchanged with '
            'source_ids=[] and okf_tags=[]; never invent support or silently discard work. '
            'Use the usual propose_questions schema. The server derives provenance groups '
            'and compares baseline/expanded models on identical splits using training CV only. ')


async def prepare_baseline(plan, wave, registry, tools, invoke):
    require(plan, wave)
    stored = read_baseline(plan, wave, required=False)
    if stored:
        return stored
    from memstara.pipeline.core import _ensure_agent, ModelConfig
    from memstara.stage_models import deployment_profiles, for_stage
    profiles = plan.get('stage_models') or deployment_profiles()
    identity = digest([plan['run_tag'], wave])[:24]
    agent = await _ensure_agent('memstara-hybrid-baseline-' + identity,
        **plan['hybrid_policy']['baseline_prompt'], model_config=ModelConfig(**for_stage(profiles, 'question')),
        pattern_config={'execution_pattern': 'reason_act'})
    allowed = [t for t in tools if (t.get('tool_name') or t.get('name')) in BASE_TOOLS]
    if {t.get('tool_name') or t.get('name') for t in allowed} != BASE_TOOLS:
        raise ValueError('Hybrid metadata catalog / freeze tools are unavailable')
    from memstara.pipeline.feature_context import instructions as feature_instructions
    prompt = (f'Write exactly one model-knowledge candidate for run {plan["run_tag"]!r}, wave {wave}. '
              'Use only CSV metadata and general biomedical knowledge. Call freeze_hybrid_candidate '
              'with questions=[one proposal], origin_run and origin_wave. Supply predictor_concepts, '
              'rationale, source_ids=[], okf_tags=[] and exact proposed_mapping with source_id="". '
              'Use 4–20 eligible distinct columns for one association; leave room for additions when '
              'scientifically justified. Do not inspect outcomes, prior results or external documents. '
              'The freeze receipt is required; do not call propose_questions or create_task.'
              + feature_instructions(baseline_scope(plan)))
    for attempt in range(2):
        token = BASE_CALL.set(True)
        try:
            await invoke(agent.id, prompt, tools=allowed, registry=registry,
                         stage=f'question-baseline{wave}-{attempt + 1}')
        finally:
            BASE_CALL.reset(token)
        stored = read_baseline(plan, wave, required=False)
        if stored:
            return stored
        prompt += ' No baseline receipt was saved. Inspect rejection feedback and repair the proposal.'
    raise ValueError('Hybrid baseline was not frozen; no graph or downstream call was started')
