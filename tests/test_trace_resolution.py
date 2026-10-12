"""Trace lookup should retain useful diagnostics for incomplete trial indexes."""

import json
import uuid

import pytest

from memstara.trace.run import _resolve


def test_missing_trial_reports_valid_ids_and_invalid_entries(tmp_path, capsys):
    index = tmp_path / "rows.json"
    index.write_text(json.dumps([{"trial": 3}, {}, {"trial": None},
                                 {"trial": "2"}, {"trial": True}, {"trial": 1}]))
    with pytest.raises(SystemExit) as error:
        _resolve(9, None, index)
    assert error.value.code == 1
    message = capsys.readouterr().err
    assert "trial 9 not found. available: [1, 3]" in message
    assert "4 invalid trial identifiers" in message


def test_existing_trial_preserves_stage_run_id(tmp_path):
    run_id = uuid.uuid4()
    index = tmp_path / "rows.json"
    index.write_text(json.dumps([{"trial": 3, "run_ids": {"hypothesis": str(run_id)}}]))
    assert _resolve(3, "hypothesis", index) == [("hypothesis", run_id)]


def test_boolean_identifier_cannot_select_another_trials_trace(tmp_path):
    run_id = uuid.uuid4()
    index = tmp_path / "rows.json"
    index.write_text(json.dumps([{"trial": True, "run_ids": {"hypothesis": str(run_id)}}]))
    with pytest.raises(SystemExit) as error:
        _resolve(1, "hypothesis", index)
    assert error.value.code == 1
