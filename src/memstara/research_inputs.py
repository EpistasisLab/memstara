"""Local research input registration and deterministic, non-inference inspection.

Registration is preparation, not permission to launch. Original files are never
changed, and dataset rows are never returned by this module.
"""

from collections import Counter
import csv
from datetime import UTC, datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import tempfile
import shutil
import uuid
from typing import Any

MAX_BYTES = 100 * 1024 * 1024
MISSING = {"", "?", "na", "nan", "null", "none", "n/a"}
FIELDS = {
    "name",
    "dataset_path",
    "knowledge_path",
    "target",
    "excluded_columns",
    "missing_policy",
    "knowledge_mode",
    "data_mode",
}
TARGET_FIELDS = {"column", "description", "positive_label", "negative_label", "prediction_time", "horizon"}


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def registry_root():
    from memstara.paths import DEFAULT_OUTPUT_DIR

    return Path(os.environ.get("MEMSTARA_RESEARCH_INPUTS_DIR") or DEFAULT_OUTPUT_DIR / "research_inputs")


def config(value):
    if not isinstance(value, dict) or set(value) - FIELDS:
        raise ValueError("Use only the documented research input fields")
    result = dict(value)
    result["knowledge_mode"] = result.get("knowledge_mode", "okf")
    result["data_mode"] = result.get("data_mode", "dataset")
    if result["knowledge_mode"] not in ("okf", "llm_only") or result["data_mode"] not in ("dataset", "proposal"):
        raise ValueError("Select supported knowledge and data modes")
    for key in ("dataset_path", "knowledge_path"):
        result.setdefault(key, "")
    if result["knowledge_mode"] == "llm_only":
        result["knowledge_path"] = ""
    if result["data_mode"] == "proposal":
        result["dataset_path"] = ""
        result["excluded_columns"] = []
    required = {"name"}
    if result["knowledge_mode"] == "okf":
        required.add("knowledge_path")
    if result["data_mode"] == "dataset":
        required.add("dataset_path")
    for key in ("name", "dataset_path", "knowledge_path"):
        if not isinstance(result.get(key), str) or (key in required and not result[key].strip()):
            raise ValueError(f"{key} is required")
        result[key] = result[key].strip()
    if len(result["name"]) > 120:
        raise ValueError("Research name must contain at most 120 characters")
    target = result.get("target", {})
    if not isinstance(target, dict) or set(target) - TARGET_FIELDS:
        raise ValueError("Unsupported target fields")
    if any(not isinstance(v, str) or len(v) > 4000 for v in target.values()):
        raise ValueError("Target values must be text, at most 4000 characters each")
    result["target"] = {key: target.get(key, "").strip() for key in sorted(TARGET_FIELDS)}
    excluded = result.get("excluded_columns", [])
    if not isinstance(excluded, list) or any(not isinstance(x, str) for x in excluded):
        raise ValueError("Excluded columns must be an array of exact column names")
    result["excluded_columns"] = sorted({x.strip() for x in excluded if x.strip()})
    result["missing_policy"] = result.get("missing_policy", "reject")
    if result["missing_policy"] != "reject":
        raise ValueError("Only reject is currently supported; no automatic imputation or row deletion")
    return result


def inspect(value):
    value = config(value)
    problems = []

    def issue(code, message):
        problems.append({"code": code, "message": message})

    dataset, before, rows = None, None, 0
    headers, predictors = [], []
    target = value["target"]
    counts: Counter[str] = Counter()
    missing: Counter[str] = Counter()
    nonfinite: Counter[str] = Counter()
    if value["data_mode"] == "dataset":
        dataset = Path(value["dataset_path"]).expanduser().resolve()
        if dataset.suffix.lower() != ".csv" or not dataset.is_file():
            raise ValueError("Select an existing local CSV file")
        if dataset.stat().st_size > MAX_BYTES:
            raise ValueError("CSV exceeds the current 100 MiB inspection limit")
        before = digest(dataset)
        target = value["target"]
        counts, missing, nonfinite = Counter(), Counter(), Counter()
        rows = 0
        try:
            with dataset.open(newline="", encoding="utf-8-sig") as stream:
                reader = csv.reader(stream, strict=True)
                headers = next(reader, [])
                if not headers or len(headers) != len(set(headers)) or any(not h.strip() for h in headers):
                    raise ValueError("CSV requires nonempty, unique column names")
                for row in reader:
                    if len(row) != len(headers):
                        raise ValueError("CSV contains a row with a different number of fields than its header")
                    rows += 1
                    for key, raw in zip(headers, row, strict=True):
                        if raw.strip().lower() in MISSING:
                            missing[key] += 1
                        else:
                            try:
                                if not math.isfinite(float(raw)):
                                    nonfinite[key] += 1
                            except ValueError:
                                pass
                        if key == target["column"]:
                            # Never expose label values until the user provides their mapping.
                            if raw == target["positive_label"] and raw not in MISSING:
                                counts["positive"] += 1
                            elif raw == target["negative_label"] and raw not in MISSING:
                                counts["negative"] += 1
                            else:
                                counts["unmapped"] += 1
        except csv.Error:
            raise ValueError(
                "CSV parsing failed. Check CSV quoting and field lengths; no source values were changed"
            ) from None
        if digest(dataset) != before:
            raise ValueError("Dataset changed during inspection; inspect a stable file again")
        if not rows:
            issue("empty_dataset", "CSV must contain data rows")
        if target["column"] not in headers:
            issue("target_column", "Select an actual target column from the dataset")
        elif not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", target["column"]):
            issue(
                "target_column_format", "Target column must use letters, digits and underscores (up to 64 characters)"
            )
        for key in ("description", "positive_label", "negative_label", "prediction_time"):
            if not target[key]:
                issue("target_" + key, f"Provide target {key.replace('_', ' ')} explicitly")
        if target["positive_label"] == target["negative_label"]:
            issue("target_mapping", "Positive and negative labels must be different")
        if counts["unmapped"]:
            issue("unmapped_target", "Target contains missing or unmapped labels; review the binary mapping")
        if target["column"] in headers and not all(counts[x] >= 2 for x in ("positive", "negative")):
            issue("target_classes", "Both target classes need sufficient observations for evaluation")
        unknown = set(value["excluded_columns"]) - set(headers)
        if unknown:
            issue("excluded_columns", "An excluded column is not in the selected dataset")
        predictors = [h for h in headers if h != target["column"] and h not in value["excluded_columns"]]
        if len(predictors) < 4:
            issue("feature_count", "At least four eligible predictors are required")
        active = set(predictors) | {target["column"]}
        if any(missing[k] for k in active):
            issue("missing_values", "Selected columns contain missing values. No rows or values were modified")
        if any(nonfinite[k] for k in active):
            issue("nonfinite_values", "Selected columns contain non-finite numbers")
        identifiers = [h for h in predictors if h.casefold() in {"id", "record_id", "patient_id", "subject_id"}]
        if identifiers:
            issue("identifier_review", "Exclude identifier columns from predictors: " + ", ".join(identifiers))

    elif not target["description"]:
        issue("target_description", "Provide a research objective or target description for proposal mode")

    root, files = None, []
    hashes: dict[str, str] = {}
    documents: list[Any] = []
    if value["knowledge_mode"] == "okf":
        root = Path(value["knowledge_path"]).expanduser().resolve()
        if not root.is_dir():
            raise ValueError("Select an existing local OKF folder")
        if not (root / "index.md").is_file():
            issue("okf_root", "Select the actual OKF bundle folder containing index.md")
        for path in root.rglob("*"):
            if not path.resolve().is_relative_to(root):
                raise ValueError("OKF documents and folders must remain inside the selected folder")
            if path.is_symlink() and path.is_dir():
                raise ValueError("OKF symlink folders are not supported; use ordinary folders inside the bundle")
        files = sorted(root.rglob("*.md"))
        hashes = {}
        for path in sorted(
            p
            for p in root.rglob("*")
            if p.is_file() and p.suffix.lower() in {".md", ".yaml", ".yml", ".json", ".jsonl"}
        ):
            if not path.resolve().is_relative_to(root):
                raise ValueError("OKF documents must remain inside the selected folder")
            hashes[str(path.relative_to(root))] = digest(path)
        if not hashes:
            issue("okf_empty", "The OKF folder contains no Markdown documents")
        # Use the same parser as execution; do not change process-global OKF settings.
        from memstara.mcp_servers.okf import _load

        documents, skipped = _load(root)
        if not documents:
            issue("okf_documents", "The runtime parser found no usable OKF documents")
        if skipped:
            issue("okf_skipped", f"The runtime parser skipped {len(skipped)} document(s); review their format")
    identity = {
        "dataset_sha256": before,
        "knowledge_hashes": hashes,
        "target": target,
        "excluded_columns": value["excluded_columns"],
        "missing_policy": value["missing_policy"],
    }
    if value["knowledge_mode"] != "okf" or value["data_mode"] != "dataset":
        identity["input_modes"] = {key: value[key] for key in ("knowledge_mode", "data_mode")}
    fingerprint = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    return {
        "configuration": {
            **value,
            "dataset_path": str(dataset) if dataset else "",
            "knowledge_path": str(root) if root else "",
        },
        "fingerprint": fingerprint,
        "dataset_sha256": before,
        "dataset": {
            "rows": rows,
            "columns": headers,
            "column_count": len(headers),
            "missing_cells": sum(missing.values()),
            "columns_with_missing": dict(missing),
            "target_counts": dict(counts),
            "eligible_predictor_count": len(predictors),
        },
        "knowledge": {
            "documents": len(documents),
            "markdown_files": len(files),
            "domains": sorted({d.domain for d in documents}),
            "hashes": hashes,
        },
        "issues": problems,
        "input_checks_passed": not problems,
        "execution_ready": False,
        "execution_note": (
            "Select a saved version in pipeline settings. Execution rechecks files, data quality "
            "and evaluation feasibility before model calls. Review skill compatibility separately."
        ),
        "inspected_at": datetime.now(UTC).isoformat(),
    }


def register(value):
    from memstara.pipeline.checkpoint import atomic_json

    result = inspect(value)
    result["id"] = uuid.uuid4().hex
    root = registry_root()
    root.mkdir(parents=True, exist_ok=True)
    atomic_json(root / (result["id"] + ".json"), result, overwrite=False)
    return result


def list_inputs():
    return [json.loads(p.read_text()) for p in sorted(registry_root().glob("*.json"))]


def load(identifier):
    if not isinstance(identifier, str) or not re.fullmatch("[a-f0-9]{32}", identifier):
        raise ValueError("Select a saved research input record")
    try:
        record = json.loads((registry_root() / f"{identifier}.json").read_text())
        if (
            not isinstance(record, dict)
            or record.get("id") != identifier
            or not isinstance(record.get("fingerprint"), str)
            or not re.fullmatch(r"[a-f0-9]{64}", record["fingerprint"])
            or not isinstance(record.get("configuration"), dict)
        ):
            raise ValueError("Invalid registration structure")
        record["configuration"] = config(record["configuration"])
        return record
    except FileNotFoundError:
        raise ValueError("Research input record no longer exists") from None
    except ValueError:
        raise ValueError(
            "Research input record is invalid. Restore the original record or inspect and save a new version"
        ) from None


def verify_materialized(profile):
    """A resume uses its frozen files, never current source files or new settings."""
    configuration = config(profile["configuration"])
    hashes = profile.get("artifact_hashes")
    required = {"dataset.csv", "matcher_rules.json"} if configuration["data_mode"] == "dataset" else set()
    if configuration["knowledge_mode"] == "okf":
        required.add("okf/index.md")
    if not isinstance(hashes, dict) or not required.issubset(hashes) or any(
        not isinstance(name, str) or not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)
        for name, value in hashes.items()
    ):
        raise ValueError("Frozen research manifest is incomplete or invalid; restore the original manifest")
    root = (registry_root() / "prepared" / profile["fingerprint"]).resolve()
    if Path(profile["root"]).resolve() != root:
        raise ValueError("Research artifacts are outside their registered location")
    for relative, expected in profile["artifact_hashes"].items():
        path = root / relative
        if not path.resolve().is_relative_to(root) or not path.is_file() or digest(path) != expected:
            raise ValueError("Frozen research files changed; restore the original files before resuming")
    actual = {str(p.relative_to(root / "okf")) for p in (root / "okf").rglob("*") if p.is_file()}
    expected = {p.removeprefix("okf/") for p in profile["artifact_hashes"] if p.startswith("okf/")}
    if actual != expected:
        raise ValueError("Frozen knowledge files changed; restore the original files before resuming")
    return profile


def prepare(identifier):
    """Revalidate sources, then publish an isolated, deterministic analysis copy.

    Only explicit exclusions and the user's binary mapping are applied. No row is
    removed, no missing value is filled, and no original file is changed.
    """
    saved = load(identifier)
    checked = inspect(saved["configuration"])
    if saved["fingerprint"] != checked["fingerprint"]:
        raise ValueError("Research inputs changed since registration. Inspect and save a new version")
    if not checked["input_checks_passed"]:
        raise ValueError("Research inputs need review: " + "; ".join(x["message"] for x in checked["issues"]))
    parent = registry_root() / "prepared"
    parent.mkdir(parents=True, exist_ok=True)
    root = (parent / checked["fingerprint"]).resolve()
    manifest = root / "manifest.json"
    if manifest.exists():
        profile = verify_materialized(json.loads(manifest.read_text()))
        return {**profile, "id": identifier, "configuration": checked["configuration"]}
    config = checked["configuration"]
    target = config["target"]
    with tempfile.TemporaryDirectory(prefix=".preparing-", dir=parent) as tmp:
        staging = Path(tmp) / "bundle"
        staging.mkdir()
        hashes = {}
        if config["data_mode"] == "dataset":
            source = Path(config["dataset_path"])
            with (
                source.open(newline="", encoding="utf-8-sig") as incoming,
                (staging / "dataset.csv").open("w", newline="", encoding="utf-8") as outgoing,
            ):
                reader = csv.DictReader(incoming)
                headers = reader.fieldnames
                if not headers or list(headers) != checked["dataset"]["columns"]:
                    raise ValueError("Dataset changed while preparing the analysis copy")
                fields = [c for c in headers if c not in config["excluded_columns"] or c == target["column"]]
                writer = csv.DictWriter(outgoing, fieldnames=fields, extrasaction="ignore")
                writer.writeheader()
                for row in reader:
                    raw = row[target["column"]]
                    if raw not in (target["positive_label"], target["negative_label"]):
                        raise ValueError("Dataset changed while preparing the analysis copy")
                    row[target["column"]] = "1" if raw == target["positive_label"] else "0"
                    writer.writerow(row)
            if digest(source) != checked["dataset_sha256"]:
                raise ValueError("Dataset changed while preparing the analysis copy")
            hashes["dataset.csv"] = digest(staging / "dataset.csv")
            (staging / "matcher_rules.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "target": target["column"],
                        "approved_by": "User research configuration; explicit exclusions already projected",
                        "exclusions": [],
                    }
                )
            )
            hashes["matcher_rules.json"] = digest(staging / "matcher_rules.json")
        for relative, expected in checked["knowledge"]["hashes"].items():
            destination = staging / "okf" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(Path(config["knowledge_path"]) / relative, destination)
            if digest(destination) != expected:
                raise ValueError("Knowledge changed while preparing the analysis copy")
            hashes["okf/" + relative] = expected
        profile = {
            "id": identifier,
            "fingerprint": checked["fingerprint"],
            "root": str(root),
            "configuration": config,
            "source_dataset_sha256": checked["dataset_sha256"],
            "artifact_hashes": hashes,
            "transformation": "explicit_exclusions_and_binary_label_mapping_v1",
        }
        if inspect(config)["fingerprint"] != checked["fingerprint"]:
            raise ValueError("Research inputs changed during preparation; save a stable version")
        (staging / "manifest.json").write_text(json.dumps(profile, indent=2))
        try:
            staging.rename(root)
        except OSError:
            if not manifest.exists():
                raise
            profile = verify_materialized(json.loads(manifest.read_text()))
    return {**profile, "id": identifier, "configuration": checked["configuration"]}


def activate(profile):
    """Called only in the dedicated pipeline child, never in the control server."""
    verify_materialized(profile)
    root = Path(profile["root"])
    from memstara.paths import output_dir

    os.environ.setdefault("MEMSTARA_USER_SKILLS_DIR", str(output_dir() / "skills"))
    os.environ.setdefault("MEMSTARA_SKILL_ALIASES_PATH", str(output_dir() / "skill_aliases.json"))
    config = profile["configuration"]
    os.environ.update(
        MEMSTARA_DATASET_PATH=str(root / "dataset.csv") if config["data_mode"] == "dataset" else "",
        AGENTIC_OKF_BUNDLE_DIR=str(root / "okf") if config["knowledge_mode"] == "okf" else "",
        MEMSTARA_OUTPUT_DIR=str(root / "derived"),
        MEMSTARA_LEAKAGE_RULES_PATH=str(root / "matcher_rules.json") if config["data_mode"] == "dataset" else "",
        MEMSTARA_OUTCOME_COLUMN=profile["configuration"]["target"]["column"],
    )
    (root / "derived").mkdir(exist_ok=True)


def ensure_matcher(profile):
    """Build once per research fingerprint, in the activated child before inference."""
    if profile["configuration"]["data_mode"] != "dataset":
        raise ValueError("Proposal mode must not build a dataset matcher")
    import fcntl
    from memstara.matcher.catalog import build_catalog, save_catalog, save_catalog_meta, meta_path
    from memstara.matcher.embedder import embed_catalog, save_embeddings, sentence_transformer_encoder
    from memstara.matcher.embedder import embeddings_path, embeddings_stamp_path
    from memstara.matcher.service import build_run_config, current_fingerprint, read_columns
    from memstara.matcher.rules import load_rules
    from memstara.pipeline.checkpoint import atomic_json

    root = Path(profile["root"])
    catalog = root / "derived" / "matcher_catalog.json"
    with (root / "derived" / ".matcher.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        rules, run_config = load_rules(), build_run_config()
        expected = current_fingerprint(run_config, rules=rules)
        stamp = catalog.with_suffix(".ready.json")
        paths = (catalog, meta_path(catalog), embeddings_path(catalog), embeddings_stamp_path(catalog))
        if stamp.exists():
            try:
                receipt = json.loads(stamp.read_text())
            except (OSError, ValueError):
                receipt = None
            hashes = receipt.get("hashes") if isinstance(receipt, dict) else None
            if (
                isinstance(receipt, dict)
                and receipt.get("fingerprint") == expected
                and isinstance(hashes, dict)
                and set(hashes) == {path.name for path in paths}
                and all(
                    path.is_file() and digest(path) == hashes[path.name]
                    for path in paths
                )
            ):
                return
        entries = build_catalog(
            read_columns(root / "dataset.csv"), outcome_col=profile["configuration"]["target"]["column"], rules=rules
        )
        texts = [entry.match_text for entry in entries]
        matrix = embed_catalog(texts, sentence_transformer_encoder(run_config.embedding))
        save_catalog(entries, catalog)
        save_embeddings(matrix, catalog, match_texts=texts, cfg=run_config.embedding)
        save_catalog_meta(entries, catalog, expected)
        atomic_json(stamp, {"fingerprint": expected, "hashes": {p.name: digest(p) for p in paths}})


def instructions(profile):
    if not profile:
        return ""
    configuration = profile["configuration"]
    target = configuration["target"]
    data = (
        "No dataset is attached. Produce a research proposal only; no training or measured metrics. "
        if configuration.get("data_mode", "dataset") == "proposal"
        else "The analysis copy encodes the specified positive label as 1 and negative label as 0. "
        "Use only available predictor columns. The target is never a predictor. "
    )
    knowledge = (
        "No OKF corpus is attached. Use model knowledge, identify it as unverified, and never invent citations. "
        if configuration.get("knowledge_mode", "okf") == "llm_only"
        else "Use only the selected corpus. Discover domains and supported filters with knowledge tools; "
        "do not assume any prior study taxonomy. "
    )
    return (
        "\n\nUSER RESEARCH CONTRACT (applies to every stage)\n"
        + json.dumps(target, ensure_ascii=False)
        + "\n"
        + data
        + knowledge
        + "Do not substitute a prior study target or assume undocumented timing or label meanings. "
        "Avoid predictors unavailable at the specified prediction time; report uncertainty explicitly.\n"
    )


def validate_skills(books):
    """Legacy corpus-specific defaults cannot silently define a different study."""
    from memstara.paths import PLAYBOOKS_DIR

    generic_hypotheses = {"hypothesis_research", "random_features"}
    for name in books.get("hypothesis", []):
        if (PLAYBOOKS_DIR / f"{name}.md").is_file() and name not in generic_hypotheses:
            raise ValueError(
                "Research inputs require a corpus-independent Hypothesis skill. "
                "Select hypothesis_research, random_features, or a reviewed custom skill"
            )
    if any(name in {"shared-anil-addiction", "shared-anil-hiv"} for name in books.get("report", [])):
        raise ValueError(
            "This research profile has no approved specialist domain binding. "
            "Select a generic Explanation skill or a reviewed custom skill"
        )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Inspect or register local research inputs without model calls")
    parser.add_argument("action", choices=("inspect", "register", "prepare"))
    parser.add_argument("input", help="Configuration JSON path, or saved record ID for prepare")
    args = parser.parse_args()
    from memstara.env import load_env
    load_env()
    try:
        result = (
            prepare(args.input)
            if args.action == "prepare"
            else {"inspect": inspect, "register": register}[args.action](json.loads(Path(args.input).read_text()))
        )
        print(json.dumps(result, indent=2))
    except (ValueError, OSError) as error:
        parser.exit(2, f"Research inputs: {error}\n")
