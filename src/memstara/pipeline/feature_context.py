"""Header-only availability context shared by every question writer in a run."""

import csv
import json
from pathlib import Path

from memstara.matcher.catalog import build_catalog


def freeze_feature_context(dataset: Path, target: str) -> dict:
    """Reuse matcher semantics; never read patient rows or infer clinical units."""
    with dataset.open(newline="", encoding="utf-8-sig") as stream:
        columns = next(csv.reader(stream), [])
    if not target or target not in columns:
        raise ValueError("Feature context requires the configured target in the dataset header")
    entries = build_catalog(columns, target)
    if not entries:
        raise ValueError("No predictors available for question generation")
    return {
        "version": "header_catalog_v1",
        "meaning_source": "matcher catalog derived from column labels; not a validated clinical data dictionary",
        "features": [
            {"column": entry.feature_name, "meaning": entry.match_text,
             "kind": entry.feature_type}
            for entry in entries
        ],
    }


def instructions(snapshot: dict | None) -> str:
    context = (snapshot or {}).get("feature_context")
    if context is None:
        return ""  # Historical snapshots retain their original experimental conditions.
    features = context.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError("Frozen feature context is empty; cannot generate data-grounded questions")
    target = snapshot.get("y_column")
    if any(row.get("column") == target for row in features):
        raise ValueError("Outcome leaked into predictor context")
    return (
        "\nAVAILABLE PREDICTORS (frozen for this run; metadata only):\n"
        + json.dumps(context, ensure_ascii=False, separators=(",", ":"))
        + ("\nFIXED BASELINE PREDICTORS (added separately by extraction): "
           + json.dumps(snapshot["comparison_policy"].get("baseline_columns", []))
           + ". Propose justified predictor concepts whose incremental value can be tested beyond this baseline. "
           "An empty list means no clinical baseline is configured. "
           if snapshot.get("comparison_policy") else "")
        + "\nBefore proposing a question, check every required predictor concept against this list. "
        "Choose a KG/OKF-supported mechanism whose necessary predictors have clinically defensible "
        "representations here. State the intended concept-to-column correspondence in the rationale. "
        "If a necessary concept is absent or its meaning is uncertain, choose another supported "
        "mechanism; do not invent a column, assume an unlisted measurement, drop an essential "
        "concept, or replace it with a merely similar diagnosis or drug. If no grounded question "
        "is feasible, propose none. Keep question concepts in clinical language. These meanings "
        "come from column labels, not patient values; units, timing and undocumented coding are "
        "unknown. Availability is not evidence of association. This context contains no ML "
        "scores or importance; the separately specified feedback policy remains in force. "
        "The answering stage must still verify mappings with the matcher and create_task contract.\n"
    )
