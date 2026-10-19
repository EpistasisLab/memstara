import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from memstara.report_inputs import execute, project


def row(trial=12):
    return {'trial': trial, 'result_id': 7, 'model': 'xgboost', 'auc': .7,
            'hypothesis': 'Question', 'interpretation': 'Measured association',
            'evaluation': {'auc': .7, 'predictions': [0] * 1000000}}


def test_projection_excludes_large_raw_payload_and_labels_omissions():
    original = row()
    original['interpretation'] = 'a' * 20000
    projected = project(original)
    assert len(json.dumps(projected)) < 18000
    assert projected['scalar_evaluation']['auc'] == .7
    assert projected['evidence_scope']['omitted_text'][0]['original_characters'] == 20000
    assert len(original['evaluation']['predictions']) == 1000000


def test_loop_is_scoped_and_raw_read_tools_are_not_available(tmp_path):
    invoke = AsyncMock(return_value=('Report', {'status': 'completed'}))
    read = AsyncMock(return_value={'results': [row()]})
    result = asyncio.run(execute({'run_tag': 'test'}, 13, tmp_path, ('agent', 'old'),
                                {'registry': None, 'tools': ['read_results']}, invoke, read))
    assert result[0] == 'Report'
    assert read.call_args.args[2] == {'run_tag': 'test', 'trial_start': 12, 'trial_end': 13}
    assert invoke.call_args.kwargs['tools'] == []
    assert len(invoke.call_args.args[1]) < 2000
    assert (tmp_path / 'report_io/loop-13.json').exists()


def test_out_of_scope_result_cannot_reach_model(tmp_path):
    invoke = AsyncMock()
    with pytest.raises(ValueError, match='outside'):
        asyncio.run(execute({'run_tag': 'test'}, 13, tmp_path, ('agent',),
                            {'registry': None}, invoke, AsyncMock(return_value={'results': [row(0)]})))
    invoke.assert_not_awaited()


def test_final_comparison_does_not_call_model(tmp_path):
    invoke = AsyncMock()
    text, entry = asyncio.run(execute({'run_tag': 'test'}, None, tmp_path, ('agent',),
                                     {'registry': None}, invoke, AsyncMock(return_value={'results': [row()]})))
    invoke.assert_not_awaited()
    assert '| 12 | 7 | xgboost | 0.7 |' in text
    assert entry['status'] == 'completed'
