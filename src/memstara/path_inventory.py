"""Inventory explicit Markdown instance rows without inferring edge provenance."""
from __future__ import annotations

import hashlib
import re
from typing import Any


def path_inventory(body: str) -> dict[str, Any]:
    """Recognize numbered tables under Instances; all other formats stay unknown.

    Row identifiers are local to the parsed source fingerprint. They are not KG
    identifiers or evidence that the agent used the row. Never inherit a document
    evidence label onto an individual path.
    """
    rows: list[dict[str, str | int]] = []
    diagnostics: list[str] = []
    section = False
    header: list[str] | None = None
    table = False
    seen: set[str] = set()
    fence: str | None = None
    for line_number, line in enumerate(body.splitlines(), 1):
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is not None:
            continue
        heading = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if heading:
            section = heading.group(1).casefold() == "instances"
            header, table = None, False
            continue
        if not section:
            continue
        if not line.strip().startswith("|"):
            header, table = None, False
            continue
        cells = [cell.strip() for cell in re.split(r"(?<!\\)\|", line.strip().strip("|"))]
        if header is None:
            if cells and cells[0] in {"#", "id", "ID"}:
                header = cells
            continue
        if not table:
            table = len(cells) == len(header) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells)
            if not table:
                diagnostics.append("unsupported_instance_table")
                header = None
            continue
        if len(cells) != len(header) or not cells[0].isdigit():
            diagnostics.append("malformed_instance_row")
            continue
        row_id = cells[0]
        if row_id in seen:
            diagnostics.append("duplicate_instance_identifier")
        seen.add(row_id)
        rows.append({"local_id": row_id, "body_line": line_number,
                     "row_sha256": hashlib.sha256(line.strip().encode()).hexdigest(),
                     "evidence_status": "unknown"})
    return {
        "version": "path_inventory_v1",
        "status": "partial" if diagnostics else "recorded" if rows else "unavailable",
        "format": "numbered_markdown_instances_table" if rows else None,
        "row_count": len(rows), "rows": rows[:25], "truncated": len(rows) > 25,
        "diagnostics": sorted(set(diagnostics)),
        "hypothesis_use": "not_assessed", "edge_provenance": "not_assessed",
    }
