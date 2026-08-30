#!/usr/bin/env python3
# SOURCE: SANDBOX-ORIGINAL — not copied from afc-forge. afc-forge exposes the
#   matcher through its own CLI, not through MCP, so it has no counterpart to
#   this file. The matcher itself lives in matcher_impl/ and IS a copy — see the
#   SOURCE banner at the top of each file there.
"""Semantic matcher MCP server — clinical concept names -> exact cohort columns.

Core launches this file as a stdio child process. The hypothesis agent calls
`match_concepts` (or `match_concept`) to turn the concepts it named into the
column names this cohort actually has.

    MEMSTARA_DATASET_PATH     the cohort CSV (its header is the catalog's source)
    MEMSTARA_OUTCOME_COLUMN   the label, excluded from the catalog and re-checked here
    MEMSTARA_OUTPUT_DIR       where the cache lives

WHAT THESE TOOLS RETURN
-----------------------
A GROUP, not an answer. The matcher's ranking is cosine over clinical text, and on
this cohort rank 1 is frequently a false friend: "hypertension" ranks
`DX__I11.0__Hypertensive heart disease` above `DX__I10__Essential hypertension`.
Neither the threshold nor the rank separates them, so the tool shows the group and
the agent judges it. See §6.7.1.

Structure only — feature_name, feature_type, similarity_score. Never a prevalence,
a coverage percentage, or any other statistic computed from patient rows: the
matcher is the one component that sees the whole column list and it must not be
the one that leaks what is in them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.resolve()
sys.path.insert(0, str(_ROOT))

from mcp.server.fastmcp import FastMCP

from debug_hook import quiet_child, wait_for_debugger

quiet_child()
wait_for_debugger("semantic-matcher")

mcp = FastMCP("semantic-matcher")


def _check_feature_type(feature_type: str | None) -> str | None:
    """An error string if the scope is not a type this catalog has, else None.

    Screened here rather than in `matcher.py`: an unknown type produces an empty
    candidate list whose note says "nothing was close enough — try rewording",
    and that advice is wrong. No amount of rewording fixes a typo in the scope.
    """
    from matcher_impl.service import valid_feature_types

    if feature_type is None or feature_type in valid_feature_types():
        return None
    return json.dumps(
        {
            "error": f"unknown feature_type {feature_type!r}",
            "valid_feature_types": list(valid_feature_types()),
            "hint": "omit feature_type to search every type",
        },
        ensure_ascii=False,
    )


@mcp.tool()
def describe_matcher() -> str:
    """Report what the matcher is holding: entry counts, the floor, the artifacts.

    Operational tool — not exposed to the agents. Use it to confirm the cache was
    built against the cohort you think it was.
    """
    from matcher_impl import config
    from matcher_impl.embedder import embeddings_path
    from matcher_impl.service import current_fingerprint, get_matcher, valid_feature_types

    try:
        matcher = get_matcher()
    except Exception as exc:  # a stale or missing cache is the expected failure
        return json.dumps(
            {
                "status": "not_ready",
                "reason": str(exc),
                "fix": "conda run -n memstara python scripts/build_matcher_cache.py",
            },
            ensure_ascii=False,
            indent=2,
        )

    by_type: dict[str, int] = {}
    for e in matcher.entries:
        by_type[e.feature_type] = by_type.get(e.feature_type, 0) + 1
    fingerprint = current_fingerprint()
    return json.dumps(
        {
            "status": "ready",
            "total_columns": len(matcher.entries),
            "by_type": by_type,
            "valid_feature_types": list(valid_feature_types()),
            "sim_threshold": matcher.config.matcher.sim_threshold,
            "top_k": matcher.config.matcher.top_k,
            "embedding_model": f"{matcher.config.embedding.model}@{matcher.config.embedding.revision}",
            "catalog_path": str(config.CATALOG_JSON),
            "embedding_path": str(embeddings_path(config.CATALOG_JSON)),
            "catalog_version": {
                "schema": fingerprint["schema_version"],
                "builder": fingerprint["builder_version"],
                "cohort_file": fingerprint["cohort_file"],
                "columns_sha1": fingerprint["columns_sha1"],
            },
            "outcome_excluded": fingerprint["outcome_col"],
        },
        ensure_ascii=False,
        indent=2,
    )


@mcp.tool()
def match_concepts(
    concepts: list[str],
    top_k: int | None = None,
    threshold: float | None = None,
    feature_type: str | None = None,
) -> str:
    """Map several clinical concepts to cohort columns in one call.

    Prefer this over `match_concept`: all the concepts are encoded in a single
    pass, so asking for ten costs about what asking for one costs.

    Each result is a GROUP of candidates ranked by similarity. The top-ranked one
    is frequently NOT the column you want — read the whole group and pick by the
    column's name and clinical meaning.

    Args:
        concepts:     the concepts to look up, e.g. ["essential hypertension",
                      "hemoglobin a1c", "tobacco use"]. Plain clinical English
                      works best; a code works best inside English, as in
                      "essential hypertension (I10)".
        top_k:        candidates per concept (default: the configured 8). Exact and
                      prefix code matches, and the levels of a categorical family,
                      are returned in addition to this budget.
        threshold:    minimum similarity (default: the calibrated floor).
        feature_type: restrict to "diagnosis" | "medication" | "lab" |
                      "demographic". Omit to search everything.

    Returns:
        JSON: {"results": [{"concept", "candidates": [{"feature_name",
        "feature_type", "similarity_score"}], "note"?}, ...]}, in the order asked.

        An empty "candidates" always comes with a "note" saying why. "nothing was
        close enough" means reword. "a code this cohort does not carry" means
        rewording will not help — name the concept in clinical English instead.
    """
    bad = _check_feature_type(feature_type)
    if bad is not None:
        return bad

    from matcher_impl.service import get_matcher

    results = get_matcher().match_many(
        concepts, feature_type=feature_type, top_k=top_k, threshold=threshold
    )
    return json.dumps({"results": [r.to_dict() for r in results]}, ensure_ascii=False)


@mcp.tool()
def match_concept(
    concept: str,
    top_k: int | None = None,
    threshold: float | None = None,
    feature_type: str | None = None,
) -> str:
    """Map one clinical concept to cohort columns. See `match_concepts` for a batch.

    Returns a GROUP: {"concept", "candidates": [...], "note"?}. Rank 1 is not the
    answer — read the group and pick the clinically correct column.
    """
    bad = _check_feature_type(feature_type)
    if bad is not None:
        return bad

    from matcher_impl.service import get_matcher

    result = get_matcher().match(
        concept, feature_type=feature_type, top_k=top_k, threshold=threshold
    )
    return json.dumps(result.to_dict(), ensure_ascii=False)


if __name__ == "__main__":
    mcp.run()
