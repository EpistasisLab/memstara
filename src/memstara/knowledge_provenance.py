"""Conservative document annotation inspection, not hypothesis novelty scoring.

Unknown corpus formats stay usable. A document read is not evidence that a
hypothesis used a particular path. Never infer provenance from folder names.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from memstara.path_inventory import path_inventory
from memstara.novelty import source_paths, score_paths


def document_provenance(fields: dict[str, Any], body: str) -> dict[str, Any]:
    """Preserve explicit source declarations and detect supported contradictions."""
    kind = fields.get("type")
    kind = kind.strip().casefold() if isinstance(kind, str) else ""
    raw = fields.get("evidence")
    evidence = raw.strip().casefold() if isinstance(raw, str) else ""
    known = {"observed", "predicted", "mixed"}
    headings = set(re.findall(
        r"^#{1,6}\s+Evidence\s*[—–:-]\s*(OBSERVED|PREDICTED|MIXED)\s*$",
        body, flags=re.I | re.M,
    ))
    declarations = {value.casefold() for value in headings}
    if evidence in known:
        declarations.add(evidence)
    diagnostics = []
    if len(declarations) > 1:
        diagnostics.append("conflicting_evidence_declarations")
    hops = fields.get("predicted_hop_count")
    valid_hops = isinstance(hops, int) and not isinstance(hops, bool) and hops >= 0
    if hops is not None and not valid_hops:
        diagnostics.append("invalid_predicted_hop_count")
    if isinstance(hops, int) and valid_hops and ((hops > 0 and "observed" in declarations)
                       or (hops == 0 and declarations & {"mixed", "predicted"})):
        diagnostics.append("predicted_hop_count_conflicts_with_evidence")
    if evidence not in known and raw is not None:
        diagnostics.append("unsupported_evidence_annotation")
    if diagnostics:
        status = "unknown"
    elif evidence in known:
        status = evidence
    elif kind == "literature evidence":
        status = "not_applicable"
    else:
        status = "unknown"
    # Hash the parsed source, never a machine-specific path or a truncated excerpt.
    try:
        canonical = json.dumps({"fields": fields, "body": body}, sort_keys=True, default=str)
        source_hash = hashlib.sha256(canonical.encode()).hexdigest()
    except (TypeError, ValueError, RecursionError):
        source_hash = None
        status = "unknown"
        diagnostics.append("source_fingerprint_unavailable")
    return {
        "version": "document_provenance_v1", "level": "document",
        "status": status, "document_type": fields.get("type") if isinstance(fields.get("type"), str) else None,
        "declared_evidence": raw if isinstance(raw, str) else None,
        "predicted_hop_count": hops if valid_hops else None,
        "schema_id": fields.get("schema_id") if isinstance(fields.get("schema_id"), str) else None,
        "diagnostics": diagnostics,
        "parsed_source_sha256": source_hash,
        "hypothesis_attribution": "not_assessed", "novelty_score": None,
        "path_inventory": path_inventory(body),
        "paths": source_paths(fields, body, status) if source_hash else [],
    }


STATUSES = ("observed", "predicted", "mixed", "unknown", "not_applicable")


def hypothesis_provenance(refs: list[str], config_path: str, *, run_tag: str,
                          trial: int, question_id: int, path_uses: Any = None) -> dict[str, Any]:
    """Resolve declared citations only against successful reads in this execution.

    This verifies document access and source annotations, not which individual
    path instances support the scientific claim. Never fill missing provenance
    from another execution, the current corpus, or an LLM's novelty judgment.
    """
    result: dict[str, Any] = {
        "version": "hypothesis_provenance_v1", "level": "cited_document",
        "run_tag": run_tag, "trial": trial, "question_id": question_id,
        "attribution": "agent_declared_sources_checked_against_run_reads",
        "path_instance_attribution": "not_assessed", "novelty_score": None,
        "counts": dict.fromkeys(STATUSES, 0), "sources": [], "diagnostics": [],
    }
    unique = list(dict.fromkeys(ref.strip() for ref in refs if ref.strip()))
    if not unique:
        result["status"] = "no_declared_sources"
        result["novelty"] = score_paths([], path_uses)
        return result
    records: list[dict[str, Any]] = []
    try:
        if not config_path:
            raise ValueError("No run audit configured")
        with (Path(config_path).resolve().parent / "knowledge_reads.jsonl").open() as stream:
            for line in stream:
                try:
                    event = json.loads(line)
                    rows = event.get("results", []) if isinstance(event, dict) else []
                    if not isinstance(rows, list):
                        raise ValueError("Invalid audit results")
                    records.extend(row for row in rows if isinstance(row, dict)
                                   and row.get("status") == "read")
                except (ValueError, TypeError):
                    result["diagnostics"].append("malformed_read_event")
    except (OSError, ValueError):
        result["diagnostics"].append("read_audit_unavailable")
    seen = set()
    for ref in unique:
        hits = [row for row in records if ref.casefold() in {
            str(row.get("id", "")).casefold(), str(row.get("ref", "")).casefold()}]
        candidates = {row.get("id") for row in hits if isinstance(row.get("id"), str)}
        source: dict[str, Any] = {"declared_ref": ref, "status": "unknown"}
        if len(candidates) == 1:
            source_id = next(iter(candidates))
            if source_id in seen:
                continue
            seen.add(source_id)
            source["id"] = source_id
            metadata = [row.get("knowledge_provenance") for row in hits]
            usable = [m for m in metadata if isinstance(m, dict)
                      and m.get("version") == "document_provenance_v1"
                      and isinstance(m.get("parsed_source_sha256"), str)
                      and m["parsed_source_sha256"]]
            fingerprints = {m["parsed_source_sha256"] for m in usable}
            if len(fingerprints) == 1 and len(usable) == len(metadata):
                chosen = usable[-1]
                source["provenance"] = chosen
                source["status"] = chosen.get("status") if chosen.get("status") in STATUSES else "unknown"
                source["verification"] = "source_annotation_from_recorded_read"
            else:
                source["diagnostic"] = "source_changed_or_provenance_unavailable"
        else:
            source["diagnostic"] = "ambiguous_reference" if candidates else "reference_not_read"
        result["sources"].append(source)
        result["counts"][source["status"]] += 1
    result["status"] = "recorded" if not result["counts"]["unknown"] else "partial_or_unknown"
    result["declared_reference_count"] = len(unique)
    result["unique_source_count"] = len(result["sources"])
    result["novelty"] = score_paths(result["sources"], path_uses)
    return result
