"""Task-scoped, server-validated Data Agent split plans for the web pipeline."""

import hashlib
import json
import math
import os
from pathlib import Path

VERSION = "agent_stratified_allocation_v2"
PREVIOUS_VERSION = "agent_stratified_allocation_v1"
TWO_WAY_VERSION = "two_way_stratified_v1"
SKILLS = {"data_training_heavy": (0.1, 0.3), "data_balanced_stratified": (0.5, 0.5)}


def request(snapshot, trial):
    version = (snapshot or {}).get("data_allocation_policy", {}).get("version")
    if version not in (VERSION, PREVIOUS_VERSION, TWO_WAY_VERSION):
        return None
    from memstara.combinations import task_books

    books = task_books(snapshot, trial).get("data", [])
    if not books and version == TWO_WAY_VERSION:
        # Older frozen runs without a data skill used the 70/30 fallback.
        manual = snapshot.get("seed_schedule", {}).get("policy") in (
            "pipeline_sequence_v1",
            "independent_pipelines",
            "fixed_experiment_v1",
        )
        books = ["data_manual_split" if manual else "data_training_heavy"]
    manual = books == ["data_manual_split"] and version == TWO_WAY_VERSION
    from memstara.skill_bases import base_for

    base = base_for(snapshot, books[0]) if len(books) == 1 else None
    if len(books) != 1 or not isinstance(base, str) or (base not in SKILLS and not manual):
        return None
    skill = books[0]
    low, high = (snapshot["evaluation"]["test_size"],) * 2 if manual else SKILLS[base]
    if version == TWO_WAY_VERSION and not manual:
        low = high = 0.3 if base == "data_training_heavy" else 0.5
    prompt = snapshot["prompts"].get(f"board/data:{skill}", snapshot["prompts"].get("board/data:", {}))
    instruction = (
        "Supply data_plan with these three fields in submit_result. "
        "Preserve all rows and exact hypothesis predictors. The server performs the split."
    )
    if version == VERSION:
        instruction = (
            "Supply data_plan with these six fields in submit_result. "
            "Randomly choose the exploration hold-out fraction, independent-reserve fraction, "
            "number of split replicates, and both integer seeds; do not derive them from a fixed code "
            "value, "
            "dataset, run name or date. The first allocation establishes the independent "
            "validation fraction and validation_seed for this run. Later Loops must reuse both "
            "validation settings exactly, and choose fresh exploration settings and a fresh "
            "seed for each Loop. "
            "Preserve all rows and exact hypothesis predictors. The server performs the split."
        )
    if version == TWO_WAY_VERSION:
        instruction = (
            "Use the recorded two-way allocation contract for the entire input dataset. "
            "Submit only test_size, seed and stratify. Do not create a validation reserve "
            "or extra inner replicates. Preserve all rows and predictors. "
            "The server performs and records the split; any CV uses training rows only."
        )
    result = {
        "version": version,
        "skill": skill,
        "skill_prompt_sha256": hashlib.sha256(json.dumps(prompt, sort_keys=True).encode()).hexdigest(),
        "minimum_test_size": low,
        "maximum_test_size": high,
        "stratify": True,
        "population": "exploration_rows_after_independent_validation_reserve",
        "balanced_meaning": "equal_train_evaluation_sizes_not_class_resampling",
        "schema": {
            "test_size": "number within skill bounds",
            "seed": "integer 0..2147483647",
            **(
                {
                    "validation_size": "fraction 0.10..0.30",
                    "validation_seed": "integer 0..2147483647",
                    "replicates": "integer 1..5",
                }
                if version == VERSION
                else {}
            ),
            "stratify": True,
        },
        "instruction": instruction,
    }
    if version == TWO_WAY_VERSION:
        result["population"] = "entire_registered_dataset"
        from memstara.seed_schedule import task_seed

        recorded_seed = task_seed(snapshot, trial)
        if recorded_seed is not None:
            result["required_data_plan"] = {"test_size": low, "seed": recorded_seed, "stratify": True}
            result["instruction"] += " Submit required_data_plan exactly; never redraw a seed on retry."
    if version == VERSION:
        partition = snapshot.get("validation_partition")
        if snapshot.get("validation_partition_policy") == "data_agent_seed_v1" and partition:
            result["required_validation_partition"] = {
                "validation_seed": partition["seed"],
                "validation_size": partition["fraction"],
            }
            result["instruction"] += " Reuse required_validation_partition exactly; do not change it."
    if snapshot.get("controlled_comparison"):
        fixed = {k: snapshot["evaluation"][k] for k in ("test_size", "seed")}
        fixed["stratify"] = True
        if version == VERSION:
            # Controlled-comparison snapshots created before the dynamic
            # reserve policy may not carry an explicit partition object.
            partition = snapshot.get("validation_partition") or {}
            fixed["validation_seed"] = partition.get("seed", snapshot["evaluation"]["seed"])
            fixed["validation_size"] = partition.get("fraction", 0.2)
            fixed["replicates"] = snapshot["evaluation"]["replicates"]
        if not low <= fixed["test_size"] <= high:
            raise ValueError("Controlled split conflicts with the selected Data skill")
        result.update(
            required_data_plan=fixed,
            instruction="Matched comparison: submit required_data_plan exactly; no split changes are allowed.",
        )
    return result


def validate(value, specification, shared):
    fields = {"test_size", "seed", "stratify"}
    if specification.get("version") == VERSION:
        fields |= {"validation_size", "validation_seed", "replicates"}
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("Data skill requires data_plan matching the complete schema from claim_task")
    if specification.get("required_data_plan") and value != specification["required_data_plan"]:
        raise ValueError("Data plan must equal the frozen split for this execution")
    fraction = value["test_size"]
    if (
        type(fraction) not in (int, float)
        or not math.isfinite(fraction)
        or not specification["minimum_test_size"] <= fraction <= specification["maximum_test_size"]
    ):
        raise ValueError("Held-out fraction is outside the selected Data skill bounds")
    if value["stratify"] is not True:
        raise ValueError("Data skill requires stratify=true")
    if type(value["seed"]) is not int or not 0 <= value["seed"] <= 2147483647:
        raise ValueError("Data split seed is outside the supported integer range")
    if "validation_size" in fields and (
        type(value["validation_size"]) not in (int, float)
        or not math.isfinite(value["validation_size"])
        or not 0.1 <= value["validation_size"] <= 0.3
    ):
        raise ValueError("Independent validation fraction must be between 0.10 and 0.30")
    if "validation_seed" in fields and (
        type(value["validation_seed"]) is not int or not 0 <= value["validation_seed"] <= 2147483647
    ):
        raise ValueError("Independent validation seed is outside the supported integer range")
    if "replicates" in fields and (type(value["replicates"]) is not int or not 1 <= value["replicates"] <= 5):
        raise ValueError("Data skill replicates must be an integer from 1 to 5")
    required_reserve = specification.get("required_validation_partition")
    if required_reserve and (
        required_reserve.get("validation_seed") != value.get("validation_seed")
        or required_reserve.get("validation_size") != value.get("validation_size")
    ):
        raise ValueError("Data plan validation settings must match the frozen independent reserve")
    from memstara.evaluation import validate as validate_evaluation

    effective = validate_evaluation(
        {
            **shared,
            "test_size": fraction,
            "seed": value["seed"],
            **({"replicates": value["replicates"]} if "replicates" in fields else {}),
        }
    )
    if specification.get("version") == TWO_WAY_VERSION:
        effective["replicates"] = 1
    if effective["seed"] + effective["replicates"] - 1 > 2147483647:
        raise ValueError("Data seed plus replicate index exceeds the supported range")
    return effective


def partition_records(frame, target, effective, snapshot):
    from memstara.evaluation import evaluation_splits
    import numpy as np

    partition = snapshot.get("validation_partition")
    two_way = snapshot.get("data_allocation_policy", {}).get("version") == TWO_WAY_VERSION
    if not partition and not two_way:
        raise ValueError("Data allocation requires the frozen independent validation reserve")
    if two_way and partition:
        raise ValueError("Two-way allocation cannot contain an independent reserve")
    rows = set(range(len(frame))) if two_way else set(partition["exploration_rows"])
    reserved = sorted(set(range(len(frame))) - rows)

    def counts(indices):
        return {str(int(k)): int(v) for k, v in frame[target].iloc[indices].value_counts().items()}

    records = []
    for seed, train, test in evaluation_splits(frame[target], effective, partition=partition):
        if len(test) != math.ceil(len(rows) * effective["test_size"]):
            raise ValueError("Too few exploration rows for the requested stratified allocation")
        records.append(
            {
                "seed": seed,
                "train_rows": train.tolist(),
                "test_rows": test.tolist(),
                "n_train": len(train),
                "n_test": len(test),
                "split_id": hashlib.sha256(test.tobytes()).hexdigest(),
                "train_class_counts": counts(train),
                "test_class_counts": counts(test),
            }
        )
    return {
        "validation_partition": (
            {
                k: partition[k]
                for k in ("version", "seed", "row_count", "reserved_count", "reserved_split_id", "status", "fraction")
            }
            if partition
            else None
        ),
        "replicates": records,
        "reserved_rows": reserved,
        "reserved_class_counts": counts(np.asarray(reserved, dtype=int)),
        "exploration_count": len(rows),
        "reserved_count": len(reserved),
    }


def prepare(value, task, snapshot, subset):
    specification = request(snapshot, task["trial"])
    if not specification:
        if value is not None:
            raise ValueError("This Data skill does not accept a split plan")
        return None
    effective = validate(value, specification, snapshot["evaluation"])
    from memstara.evaluation import validate_clean_dataset
    import pandas as pd

    frame = validate_clean_dataset(Path(subset), task["y_column"], allow_missing=effective["engine"] == "xgboost")
    config = os.environ.get("MEMSTARA_RUN_CONFIG")
    archived = Path(config).parent / "feature_reproduction/input.csv" if config else None
    original = archived if archived and archived.is_file() else Path(os.environ["MEMSTARA_DATASET_PATH"])
    if hashlib.sha256(original.read_bytes()).hexdigest() != snapshot["dataset_sha256"]:
        raise ValueError("Source dataset differs from the frozen run input")
    from memstara.research_inputs import MISSING

    source = pd.read_csv(original, na_values=list(MISSING))
    try:
        pd.testing.assert_frame_equal(
            frame, source[list(frame.columns)], check_dtype=False, check_exact=False, rtol=1e-12, atol=0
        )
    except (AssertionError, KeyError):
        raise ValueError("Extraction changed rows, values or row order; preserve the source dataset") from None
    reserve_snapshot = snapshot
    if snapshot.get("validation_partition_policy") == "data_agent_seed_v1":
        partition = snapshot.get("validation_partition")
        if partition is None:
            from memstara.evaluation import discovery_partition

            partition = discovery_partition(frame[task["y_column"]], value["validation_seed"], value["validation_size"])
            partition_path = None
            config = os.environ.get("MEMSTARA_RUN_CONFIG")
            if config:
                from memstara.pipeline.checkpoint import atomic_json

                partition_path = Path(config).parent / "validation_partition.json"
                try:
                    # Publish once across workers; an exists/replace sequence can
                    # approve different reserves for simultaneous first tasks.
                    atomic_json(partition_path, partition, overwrite=False)
                except FileExistsError:
                    partition = json.loads(partition_path.read_text())
        if partition["seed"] != value["validation_seed"] or partition["fraction"] != value["validation_size"]:
            raise ValueError(
                "Data plan must match the frozen independent reserve; "
                "refresh the task allocation requirements before resubmitting"
            )
        reserve_snapshot = {**snapshot, "validation_partition": partition}
    return {
        "version": specification["version"],
        "request": specification,
        "agent_plan": value,
        "effective_evaluation": effective,
        "trial": task["trial"],
        "task_id": task["task_id"],
        "run_tag": snapshot["run_tag"],
        "config_hash": snapshot["config_hash"],
        "dataset_sha256": snapshot["dataset_sha256"],
        "subset_sha256": hashlib.sha256(Path(subset).read_bytes()).hexdigest(),
        **partition_records(frame, task["y_column"], effective, reserve_snapshot),
    }


def load_effective(path, snapshot, default):
    """ML uses only a verified server handoff, never ML-agent split overrides."""
    sidecar = Path(path).with_suffix(".comparison.json")
    if not sidecar.exists():
        if (snapshot or {}).get("data_allocation_policy"):
            raise ValueError("Data handoff is required before ML evaluation")
        return default, None
    context = json.loads(sidecar.read_text())
    record = context.get("data_allocation")
    required = request(snapshot, context.get("trial", 0))
    if required and not record:
        raise ValueError("Selected Data skill has no accepted split plan")
    if not record:
        return default, None
    recorded_request = dict(record["request"])
    required_request = dict(required) if required else None
    if required_request is not None:
        # This per-task handoff may have been made before the first allocation
        # published the run-level reserve; the reserve requirement is validated
        # separately against the submitted seed below.
        suffix = " Reuse required_validation_partition exactly; do not change it."
        for request_record in (recorded_request, required_request):
            request_record.pop("required_validation_partition", None)
            instruction = request_record.get("instruction", "")
            if instruction.endswith(suffix):
                request_record["instruction"] = instruction[: -len(suffix)]
    if (
        recorded_request != required_request
        or record["config_hash"] != snapshot["config_hash"]
        or record["subset_sha256"] != hashlib.sha256(Path(path).read_bytes()).hexdigest()
    ):
        raise ValueError("Data allocation handoff differs from this task or run")
    effective = validate(record["agent_plan"], required, snapshot["evaluation"])
    from memstara.evaluation import validate_clean_dataset

    frame = validate_clean_dataset(Path(path), snapshot["y_column"], allow_missing=effective["engine"] == "xgboost")
    rebuilt = partition_records(frame, snapshot["y_column"], effective, snapshot)
    if effective != record["effective_evaluation"] or any(record[k] != v for k, v in rebuilt.items()):
        raise ValueError("Saved Data allocation does not reproduce its recorded split")
    return effective, record
