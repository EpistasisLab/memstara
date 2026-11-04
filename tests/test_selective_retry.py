"""Selective retries retain completed outcomes and original schedule identities."""

import asyncio
import json
from types import SimpleNamespace

import pytest

from memstara.control.retry import configuration_for_retry
from memstara.pipeline.retry_selection import pending_loops, validate_loops, from_arguments
from memstara.pipeline.exploration import rounds
from memstara.seed_schedule import create, VERSION

COMPLETED = [17, 18, 20, 21, 24, 25, 26, 27, 28, 29, 30, 31, 32, 34, 36, 37]


@pytest.fixture
def source(tmp_path, monkeypatch):
    outcomes = {
        str(i): {"outcome": "completed" if i in COMPLETED else "blocked" if i in (19, 33, 35, 38) else "skipped"}
        for i in range(1, 39)
    }
    frozen = {
        "combination_plan": {"total_loops": 80, "skills": {"hypothesis": [{"id": "fixture"}]}},
        "seed_policy": VERSION,
        "seed_schedule": create(80, 1, "independent_pipelines"),
        "dataset_sha256": "fixed",
        "y_column": "target",
        "explanation_words": 250,
    }
    docs = {
        "pipeline_status.json": {"status": "failed", "loop": 38},
        "resume_arguments.json": {"pipeline_id": "p", "run_tag": "r", "waves": 80, "research_input_id": "hiv"},
        "config.json": frozen,
        "iteration_outcomes.json": outcomes,
    }
    for name, doc in docs.items():
        (tmp_path / name).write_text(json.dumps(doc))
    monkeypatch.setattr("memstara.combinations.validate_plan", lambda plan: plan)
    return {"run_dir": str(tmp_path), "run_tag": "r"}, {"research_input_id": "hiv", "waves": 80}, frozen


def test_real_80_condition_failure_pattern_preserves_source_and_seeds(source, tmp_path):
    record, configuration, frozen = source
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    retry = configuration_for_retry(record, configuration, "p", incomplete=True)
    selected = retry["_retry_loops"]
    assert len(selected) == 64
    assert not set(selected).intersection(COMPLETED)
    assert set(range(39, 81)) <= set(selected)
    assert retry["_retry_from_loop"] == 1 and retry["waves"] == 80
    assert retry["_retry_combination_plan"] == frozen["combination_plan"]
    assert retry["_retry_seed_schedule"]["seed_schedule"] == frozen["seed_schedule"]
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with pytest.raises(ValueError, match="Earlier unfinished"):
        configuration_for_retry(record, configuration, "p")  # Existing strict mode remains explicit.


def test_followup_retry_does_not_reintroduce_previously_completed_combinations():
    saved = {"retry_loops": "[1, 2, 19, 38, 39, 80]"}
    assert pending_loops({"1": {"outcome": "completed"}, "2": {"outcome": "blocked"}}, 80, saved) == [2, 19, 38, 39, 80]


@pytest.mark.parametrize("value", [[], [True], [0], [81], [2, 1], [2, 2], "1,2"])
def test_bad_selection_is_rejected(value):
    with pytest.raises(ValueError):
        validate_loops(value, 80)


def test_selection_requires_source_and_matching_start():
    args = SimpleNamespace(retry_loops="[2, 5]", retry_source_run="", start_loop=2)
    with pytest.raises(ValueError):
        from_arguments(args, 80)
    args.retry_source_run = "source"
    assert from_arguments(args, 80) == [2, 5]
    args.start_loop = 1
    with pytest.raises(ValueError):
        from_arguments(args, 80)


def test_sparse_scheduler_keeps_original_ordinals_and_resume_position(tmp_path):
    async def collect(start):
        return [i async for i in rounds(80, False, tmp_path, start=start, selected=[1, 19, 38, 80])]

    assert asyncio.run(collect(0)) == [0, 18, 37, 79]
    assert asyncio.run(collect(19)) == [37, 79]


def test_completed_source_and_changed_data_are_rejected(source, tmp_path):
    record, config, _ = source
    with pytest.raises(ValueError, match="Research source changed"):
        configuration_for_retry(record, {**config, "research_input_id": "other"}, "p", incomplete=True)
    (tmp_path / "pipeline_status.json").write_text('{"status":"completed"}')
    with pytest.raises(ValueError, match="No unfinished"):
        configuration_for_retry(record, config, "p", incomplete=True)


def test_request_passes_server_owned_selection(monkeypatch):
    monkeypatch.setattr("memstara.stage_models.deployment_profiles", lambda: {})
    monkeypatch.setenv("MEMSTARA_HYPOTHESIS_PROVIDER", "openai")
    monkeypatch.setenv("MEMSTARA_HYPOTHESIS_MODEL", "test-deployment")
    from memstara.control.request import build_argv

    argv = build_argv(
        {
            "waves": 4,
            "_retry_from_loop": 2,
            "_retry_source_run": "source",
            "_retry_loops": [2, 4],
        },
        [],
    )
    assert json.loads(argv[argv.index("--retry-loops") + 1]) == [2, 4]
    assert argv[argv.index("--start-loop") + 1] == "2"
