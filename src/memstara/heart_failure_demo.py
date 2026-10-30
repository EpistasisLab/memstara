"""Create an explicit complete-case installation demo without modifying donor data."""

import csv
import hashlib
import json
from pathlib import Path

FEATURES = (
    "age_years",
    "sex",
    "previous_myocardial_infarctions_count",
    "essential_hypertension_stage",
    "diabetes_mellitus_history",
    "obesity_history",
    "chronic_bronchitis_history",
    "bronchial_asthma_history",
)
TARGET = "chronic_heart_failure"
MISSING = {"", "?", "na", "nan", "null", "none", "n/a"}


def prepare(source, corpus, destination):
    source, corpus, destination = Path(source).resolve(), Path(corpus).resolve(), Path(destination).resolve()
    if destination.exists():
        raise ValueError("Destination exists; choose a new directory to preserve prior evidence")
    if not (corpus / "index.md").is_file():
        raise ValueError("Knowledge root must contain index.md")
    original = source.read_bytes()
    sha = hashlib.sha256(original).hexdigest()
    kept, dropped, total = [], 0, 0
    with source.open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not set((*FEATURES, TARGET)).issubset(reader.fieldnames or []):
            raise ValueError("Required documented demo columns are missing")
        for row in reader:
            total += 1
            if row[TARGET] not in {"0", "1"}:
                raise ValueError("Target labels must be explicitly encoded as 0/1; source unchanged")
            if any(row[k].strip().lower() in MISSING for k in FEATURES):
                dropped += 1
                continue
            kept.append({k: row[k] for k in (*FEATURES, TARGET)})
    if not kept or {r[TARGET] for r in kept} != {"0", "1"}:
        raise ValueError("The demo requires both target classes after complete-case selection")
    if hashlib.sha256(source.read_bytes()).hexdigest() != sha:
        raise ValueError("Source changed during preparation")
    destination.mkdir(parents=True)
    csv_path = destination / "dataset.csv"
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=[*FEATURES, TARGET])
        writer.writeheader()
        writer.writerows(kept)
    config = {
        "name": "Heart failure complete-case software demonstration",
        "dataset_path": str(csv_path),
        "knowledge_path": str(corpus),
        "excluded_columns": [],
        "missing_policy": "reject",
        "target": {
            "column": TARGET,
            "positive_label": "1",
            "negative_label": "0",
            "description": (
                "Classify the supplied heart failure indicator. Software demonstration only; "
                "clinical endpoint adjudication is unverified."
            ),
            "prediction_time": (
                "Demo assumes age, sex and prior-history fields are available at admission. "
                "Source timing requires clinical review."
            ),
            "horizon": "Not established by the supplied files; do not claim prospective risk prediction.",
        },
    }
    (destination / "research.json").write_text(json.dumps(config, indent=2) + "\n")
    evidence = {
        "source_sha256": sha,
        "derived_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
        "source_rows": total,
        "retained_rows": len(kept),
        "excluded_rows": dropped,
        "features": FEATURES,
        "policy": "complete cases on the eight fixed predictors; no imputation",
        "purpose": "installation acceptance, not clinical validation",
        "limitations": "Complete-case selection may bias the sample; endpoint timing is unverified.",
    }
    (destination / "preparation.json").write_text(json.dumps(evidence, indent=2) + "\n")
    return evidence
