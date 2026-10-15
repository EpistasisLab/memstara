"""Web selection contract, server persistence and pre-training guards; no model calls."""
import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from memstara.pipeline import feature_selection as fs
from memstara.pipeline import question_contract as qc


def plan(mode='guided', size=30):
    stages = ('hypothesis', 'data', 'ml', 'interpreter', 'report')
    schedule = {'version': 1, 'total_loops': 200, 'combinations': 1,
                'skills': {s: [{'id': ('random_features' if mode == 'random' else 'guided')
                               if s == 'hypothesis' else s}] for s in stages}}
    value = {'run_tag': 'test', 'pipeline_id': 'pipeline', 'y_column': 'Y', 'trials': 1,
             'dataset_sha256': 'synthetic', 'config_hash': 'frozen', 'evaluation': {'seed': 42},
             'combination_plan': schedule, 'comparison_policy': {'baseline_columns': []},
             'hypothesis_policy': {'question_contract': qc.VERSION},
             'recovery_policy': {'version': 'artifact_checked_v1'},
             'feature_context': {'features': [{'column': f'x{i}'} for i in range(size)]}}
    value['feature_selection_policy'] = fs.freeze(value)
    return value


@pytest.mark.parametrize('size,accepted', [(3, False), (4, True), (20, True), (21, False)])
def test_guided_count_boundaries(size, accepted):
    p = plan()
    columns = [f'x{i}' for i in range(size)]
    if accepted:
        record = fs.validate(columns, p, 0)
        assert record['actual_count'] == size and record['features'] == columns
        assert record['mode'] == 'guided' and record['seed'] is None
    else:
        with pytest.raises(ValueError, match='4–20'):
            fs.validate(columns, p, 0)


@pytest.mark.parametrize('columns', [['x0'] * 4, ['x0','x1','x2','Y'],
                                    ['x0','x1','x2','unknown'], ['x0','x1','x2',None]])
def test_invalid_predictors_cannot_be_submitted(columns):
    with pytest.raises(ValueError):
        fs.validate(columns, plan(), 0)


def test_random_sample_repeats_after_serialization_and_spans_inclusive_range():
    p = plan('random')
    sizes = set()
    for wave in range(200):
        ctx = fs.context(p, wave)
        assert ctx == fs.context(json.loads(json.dumps(p)), wave)
        columns = ctx['required_features']
        sizes.add(len(columns))
        assert len(set(columns)) == len(columns)
        assert fs.validate(columns, p, wave)['seed'] == ctx['seed']
        with pytest.raises(ValueError):
            fs.validate(list(reversed(columns)), p, wave)
    assert min(sizes) == 4 and max(sizes) == 20
    assert len(fs.context(plan('random', 4), 0)['required_features']) == 4
    with pytest.raises(ValueError, match='at least four'):
        plan('random', 3)


def test_no_silent_baseline_additions_or_changes_to_selected_pipeline():
    p = plan()
    p['comparison_policy']['baseline_columns'] = ['x0']
    with pytest.raises(ValueError, match='empty fixed baseline'):
        fs.freeze(p)
    assert fs.validate(['one'], {}, None) is None
    assert fs.instructions({}, 0) == ''
    assert fs.scoped(None, 0) is None


def random_contract(p, wave=0):
    columns = fs.context(p, wave)['required_features']
    return qc.make_contract({'predictor_concepts': columns, 'origin_wave': wave,
                             'rationale': 'Randomly sampled predictor control.',
                             'source_ids': [], 'okf_tags': []}, p)


def test_random_contract_has_no_fabricated_sources_and_supports_repeated_control():
    p = plan('random', 4)
    p['hypothesis_policy']['version'] = 'iterative_discovery_v1'
    contract = random_contract(p)
    assert contract['kind'] == 'random_feature_control'
    assert contract['evidence_mode'] == 'no_okf'
    assert qc.validate_saved(contract, qc.question_text(contract), p) == contract
    assert qc.question_text(random_contract(p, 1)) != qc.question_text(contract)
    with pytest.raises(ValueError):
        qc.make_contract({**contract, 'source_ids': ['fabricated']}, p)
    with pytest.raises(ValueError):
        qc.make_contract({**contract, 'predictor_concepts': ['changed']}, p)


def test_random_question_proposal_and_task_persist_server_provenance(monkeypatch):
    pytest.importorskip('motoro')
    from memstara.mcp_servers import blackboard as bb
    p = plan('random')
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: p)
    monkeypatch.setattr(bb, '_pipeline_run', lambda: 'test')
    conn = AsyncMock()
    conn.transaction = MagicMock(return_value=AsyncMock())
    conn.fetch.return_value = []
    conn.fetchval.return_value = 7
    monkeypatch.setattr(bb.asyncpg, 'connect', AsyncMock(return_value=conn))
    contract = random_contract(p)
    proposal = json.loads(asyncio.run(bb.propose_questions([contract], origin_run='test', origin_wave=0)))
    assert proposal['added'] and not proposal['rejected'], proposal
    columns = contract['predictor_concepts']
    conn.fetchrow.side_effect = [{'text': qc.question_text(contract), 'question_contract': contract,
                                 'origin_run': 'test', 'claimed_run': 'test'}, None]
    result = json.loads(asyncio.run(bb.create_task('test', 0, qc.question_text(contract),
        qc.hypothesis_text(contract), columns, 'Y', [], 7,
        [{'concept': c, 'column': c, 'source_id': '', 'rationale': 'Recorded random predictor'} for c in columns])))
    assert result.get('task_id') == 7, result
    payload = json.loads(conn.fetchval.call_args.args[-1])
    assert payload['feature_selection'] == fs.validate(columns, p, 0)
    conn.reset_mock()
    bad = json.loads(asyncio.run(bb.create_task('test', 0, 'question', 'hypothesis', columns[:-1], 'Y')))
    assert bad['code'] == 'invalid_feature_selection'
    conn.fetchval.assert_not_called()


def test_data_handoff_blocks_changed_predictors_before_ml(tmp_path, monkeypatch):
    from memstara.comparisons import write_context
    p = plan('random')
    columns = fs.context(p, 0)['required_features']
    monkeypatch.setenv('MEMSTARA_OUTPUT_DIR', str(tmp_path))
    path = tmp_path / 'subset.csv'
    path.write_text(','.join(columns + ['Y']) + '\n')
    task = {'trial': 0, 'columns': columns, 'y_column': 'Y',
            'evaluation': {'feature_selection': fs.validate(columns, p, 0)}}
    write_context(path, task, p)
    path.write_text(','.join(columns[:-1] + ['Y']) + '\n')
    with pytest.raises(ValueError, match='exactly'):
        write_context(path, task, p)
    task['evaluation']['feature_selection']['seed'] += 1
    with pytest.raises(ValueError, match='provenance'):
        write_context(path, task, p)


@pytest.mark.parametrize('standalone', [False, True])
def test_web_launch_freezes_policy_and_delivers_random_input(monkeypatch, tmp_path, standalone):
    pytest.importorskip('motoro')
    from memstara.control import catalog
    from memstara.control.request import build_argv
    from memstara.control.workspace import PipelineWorkspace
    from memstara.pipeline.snapshot import freeze
    from memstara.pipeline import board
    stages = ('hypothesis', 'data', 'ml', 'interpreter', 'report')
    choices = {s: ['random_features' if s == 'hypothesis' else s] for s in stages}
    monkeypatch.setattr(catalog, 'resolve', lambda k: {'id': k, 'title': k, 'hash': k,
                                                     'stage': 'hypothesis' if k == 'random_features' else k})
    monkeypatch.setenv('MEMSTARA_LLM_PROVIDER', 'openai')
    monkeypatch.setenv('MEMSTARA_LLM_MODEL', 'test-model')
    monkeypatch.delenv('MEMSTARA_STUDY_POLICY', raising=False)
    config = PipelineWorkspace.configuration({'combination_skills': choices, 'combination_max_loops': 2})
    argv = build_argv(config, [], [x[0] for x in choices.values()], stages)
    schedule = argv[argv.index('--combination-plan') + 1]
    dataset = tmp_path / 'data.csv'
    dataset.write_text('BMI,CURRENT_AGE,DX__A__One,DX__B__Two,Y\n' +
                       ''.join(f'{20+i%5},{30+i%7},{i%2},{(i+1)%2},{i%2}\n' for i in range(100)))
    monkeypatch.setenv('MEMSTARA_DATASET_PATH', str(dataset))
    monkeypatch.setenv('MEMSTARA_RUN_CONFIG', '')
    monkeypatch.setenv('MEMSTARA_OUTCOME_COLUMN', '')
    monkeypatch.setattr('memstara.pipeline.snapshot.load_prompt', lambda *a: {'system_prompt': 'test', 'goal': 'test'})
    args = SimpleNamespace(run_tag='test', question='', hypothesis_agents=1, y_column='Y',
                           evaluation=json.dumps({'engine':'logistic_regression'}), trials=1, waves=2,
                           combination_plan='' if standalone else schedule, interpret_agents=1,
                           pipeline_id='test', continuous=False, resume=False, report_only=False)
    if standalone:
        from memstara.pipeline.preparation import normalize_random_selection
        normalize_random_selection(args, choices)
    frozen = freeze(args, tmp_path, choices)
    assert frozen['hypothesis_policy']['version'] == 'knowledge_only_v1'
    assert frozen['hypothesis_policy']['combination_questions'] == 'independent_combination_questions_v1'
    assert frozen['hypothesis_policy']['prior_ml_feedback'] is False
    assert frozen['feature_selection_policy']['minimum'] == 4
    assert frozen['feature_selection_policy']['maximum'] == 20
    assert fs.context(frozen, 0)['mode'] == 'random'
    assert fs.context(frozen, 0) == fs.context(json.loads(json.dumps(frozen)), 0)
    assert fs.hypothesis_tools([{'tool_name': 'okf_read', 'server': 'okf'},
                                {'tool_name': 'match_concepts'}, {'tool_name': 'create_task'}],
                               frozen, 0) == [{'tool_name': 'create_task'}]
    monkeypatch.setattr('memstara.evaluation.active_plan', lambda: frozen)
    monkeypatch.setattr(board, 'call_board_tool', AsyncMock(return_value={'questions': []}))
    agent = AsyncMock()
    monkeypatch.setattr(board, 'call_agent', agent)
    asyncio.run(board.questions_for_wave(None, {'hypothesis': 'test-agent'}, {'question': []},
                                        run_tag='test', wave=0, want=1))
    prompt = agent.call_args.args[1]
    assert 'FEATURE SELECTION INPUT' in prompt and 'required_features' in prompt
    for column in fs.context(frozen, 0)['required_features']:
        assert column in prompt


def test_random_tool_boundary_does_not_disable_guided_mapping():
    tools = [{'server': 'okf', 'tool_name': 'okf_read'},
             {'tool_name': 'match_concepts'}, {'tool_name': 'create_task'}]
    assert fs.hypothesis_tools(tools, plan('random'), 0) == tools[2:]
    assert fs.hypothesis_tools(tools, plan(), 0) == tools
    assert fs.hypothesis_tools(tools, {}, 0) == tools


def test_measured_result_cannot_claim_different_features():
    p = plan()
    selected = fs.validate(['x0', 'x1', 'x2', 'x3'], p, 0)
    assert fs.validate_measured(['x3', 'x2', 'x1', 'x0'], selected)
    for features in (['x0', 'x1', 'x2'], ['x0', 'x1', 'x2', 'Y'], ['x0'] * 4, None):
        with pytest.raises(ValueError, match='Measured predictors'):
            fs.validate_measured(features, selected)
