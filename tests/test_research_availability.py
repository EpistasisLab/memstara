from memstara.research_inputs import current_availability


def test_moved_source_is_not_offered_as_ready(tmp_path):
    csv = tmp_path / "dataset.csv"
    csv.write_text("a,b\n1,0\n")
    okf = tmp_path / "okf"
    okf.mkdir()
    record = {"input_checks_passed": True, "configuration": {
        "dataset_path": str(csv), "knowledge_path": str(okf)}, "issues": []}
    assert current_availability(record)["input_checks_passed"]
    csv.rename(tmp_path / "moved.csv")
    result = current_availability(record)
    assert not result["input_checks_passed"]
    assert result["issues"][0]["code"] == "source_unavailable"
    assert record["input_checks_passed"]  # immutable historical inspection
    assert record["issues"] == []


def test_missing_knowledge_and_optional_sources(tmp_path):
    record = {"input_checks_passed": True, "configuration": {
        "data_mode": "proposal", "knowledge_mode": "okf",
        "knowledge_path": str(tmp_path / "missing")}}
    assert not current_availability(record)["input_checks_passed"]
    record["configuration"]["knowledge_mode"] = "llm_only"
    assert current_availability(record)["input_checks_passed"]


def test_availability_never_promotes_failed_inspection(tmp_path):
    record = {"input_checks_passed": False, "configuration": {
        "data_mode": "proposal", "knowledge_mode": "llm_only"}}
    assert not current_availability(record)["input_checks_passed"]
