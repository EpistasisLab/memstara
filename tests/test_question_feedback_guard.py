"""Prospective metrics are not observed feedback; empty questions stop before reports."""
import json

import pytest

from memstara.pipeline.question_contract import knowledge_text
from memstara.pipeline.question_repair import require_executable_questions
from memstara.pipeline.failures import PipelineExecutionFailure, ensure_not_failed, stop_execution


@pytest.mark.parametrize("text", [
    "What would weaken the hypothesis: the psychiatric/SUD group contributing no incremental "
    "AUC over the substance-use and anemia indicators alone, or the anxiety/insomnia codes "
    "mapping to near-empty columns.",
    "We will evaluate AUROC on the held-out partition.",
    "SHAP and permutation importance will help evaluate the proposed mechanism.",
    "Feature importance will be inspected after training, not used to select this question.",
])
def test_prospective_evaluation_is_not_rejected(text):
    assert knowledge_text(text, "rationale") == text


@pytest.mark.parametrize("text,cue", [
    ("Prior trials had AUC 0.75 so reuse those features.", "Prior trials"),
    ("Previous experiments support these predictors.", "Previous experiments"),
    ("Select successful features from the last run.", "successful features"),
    ("Use negative importance columns.", "negative importance"),
    ("We observed an AUROC of 0.91.", "observed an AUROC"),
    ("SHAP showed that these predictors mattered.", "SHAP showed"),
    ("AUC was 0.83 in the experiment.", "AUC was"),
])
def test_observed_feedback_is_rejected_with_actionable_cue(text, cue):
    with pytest.raises(ValueError) as error:
        knowledge_text(text, "rationale")
    assert cue in str(error.value)
    assert "without lineage" in str(error.value)


def test_empty_question_bank_stops_and_preserves_primary_cause(tmp_path):
    with pytest.raises(PipelineExecutionFailure):
        require_executable_questions([], tmp_path, 0)
    failure = json.loads((tmp_path / "pipeline_failure.json").read_text())
    assert failure["code"] == "question_generation_exhausted"
    assert failure["stage"] == "question"
    assert failure["loop"] == 1
    with pytest.raises(PipelineExecutionFailure):
        ensure_not_failed(tmp_path)
    # Even a cleanup failure must not replace the actionable first cause.
    with pytest.raises(PipelineExecutionFailure):
        stop_execution(tmp_path, "report", None, RuntimeError("Missing report"))
    assert json.loads((tmp_path / "pipeline_failure.json").read_text()) == failure
    assert not (tmp_path / "report_status.json").exists()


def test_saved_question_allows_downstream_execution(tmp_path):
    require_executable_questions([{"question_id": 1}], tmp_path, 0)
    assert not list(tmp_path.iterdir())
