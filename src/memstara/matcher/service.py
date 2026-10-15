# SOURCE: SANDBOX-ORIGINAL — not copied from afc-forge. This file exists so that
#   the ported files stay copies: everything EcoXAI-specific is collected here
#   rather than edited into matcher.py. Do not move code from here into a ported
#   file; that is what makes the port checkable with a diff.
"""The single home for sandbox glue — one matcher per process.

`matcher.py` is a byte-for-byte port of afc-forge. The moment a singleton or an
environment lookup goes inside it, the claim "this is identical to upstream" can
no longer be checked with a diff. So everything EcoXAI needs — which CSV, which
outcome column, how an encoder is obtained — lives here instead.
"""

from __future__ import annotations

import csv
import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path

import numpy as np

from memstara.matcher import config as cfg_mod
from memstara.matcher.catalog import CatalogEntry, catalog_fingerprint
from memstara.matcher.config import RunConfig
from memstara.matcher.rules import load_rules
from memstara.matcher.embedder import sentence_transformer_encoder
from memstara.matcher.matcher import Match, Matcher, MatchResult

log = logging.getLogger(__name__)

#: Every feature_type `_parse_column` can produce. Filtering on a type outside
#: this set makes the matcher return an empty result whose note says "reword" —
#: which is the wrong advice. The tool wrapper screens against this list first.
FEATURE_TYPES = ("diagnosis", "medication", "lab", "demographic")


def medication_name(value: str) -> str:
    """Normalise spelling separators only; never infer brands, salts or synonyms."""
    value = value.strip().casefold()
    if value.startswith("med__"):
        value = value[5:]
    return re.sub(r"[\s_-]+", " ", value).strip()


class VerifiedMatcher(Matcher):
    """Keep the ported ranking intact, then require medication name identity.

    A semantic score cannot establish that two drugs are the same. Medication
    classes and unregistered synonyms require an explicit mapping, not a guess.
    Diagnosis/lab/demographic candidate ranking is unchanged.
    """

    def __init__(self, entries, embeddings, *, encoder, config=None):
        matrix = np.asarray(embeddings, dtype=np.float32)
        if matrix.ndim != 2 or matrix.shape[1] == 0 or not np.isfinite(matrix).all():
            raise ValueError(
                "Invalid matcher embedding matrix: expected finite two-dimensional vectors. "
                "Rebuild the matcher cache before running."
            )
        super().__init__(entries, matrix, encoder=encoder, config=config)

    def match_many(self, concepts, *, feature_type=None, top_k=None, threshold=None):
        results = super().match_many(
            concepts, feature_type=feature_type, top_k=top_k, threshold=threshold,
        )
        medications: dict[str, list[CatalogEntry]] = {}
        for entry in self.entries:
            if entry.feature_type == "medication":
                medications.setdefault(medication_name(entry.feature_name), []).append(entry)
        verified = []
        for result in results:
            exact = medications.get(medication_name(result.concept), [])
            if exact and feature_type in (None, "medication"):
                # Name identity must not be lost to top-k or embedding thresholds.
                matches = tuple(Match(e.feature_name, "medication", 1.0) for e in exact)
                verified.append(MatchResult(result.concept, matches))
                continue
            matches = tuple(m for m in result.matches if m.feature_type != "medication")
            rejected = len(matches) != len(result.matches) or feature_type == "medication"
            note = result.note
            if rejected:
                note = (
                    "No exact medication name is present in this cohort catalog. "
                    "Semantically similar drugs were not substituted. This does not establish "
                    "absence of a brand, synonym or drug class; those require a verified mapping."
                )
            verified.append(MatchResult(result.concept, matches, note))
        return verified


def valid_feature_types() -> tuple[str, ...]:
    return FEATURE_TYPES


def dataset_path() -> Path:
    """The cohort CSV. **No fallback.**

    The previous version fell back to `outputs/dataset.csv` (a 41-column NHANES
    file) when this was unset, and silently built a 41-entry catalog. The matcher
    then works perfectly and the agent concludes the columns it wants are simply
    not in the cohort — nobody ever sees an error.
    """
    raw = os.environ.get("MEMSTARA_DATASET_PATH", "").strip()
    if not raw:
        raise RuntimeError(
            "MEMSTARA_DATASET_PATH is not set. There is no default: the fallback that "
            "used to live here silently built a 41-entry catalog from a different cohort."
        )
    p = Path(raw).expanduser().resolve()
    if not p.exists():
        raise FileNotFoundError(f"MEMSTARA_DATASET_PATH points at {p}, which does not exist.")
    return p


def outcome_column() -> str:
    """The label column. Fails rather than defaulting.

    A literal here goes quietly wrong the first time the cohort changes.
    """
    raw = os.environ.get("MEMSTARA_OUTCOME_COLUMN", "").strip()
    if not raw:
        raise RuntimeError(
            "MEMSTARA_OUTCOME_COLUMN is not set. The catalog must know which column is "
            "the label so it can be excluded; guessing it is how a label reaches an agent."
        )
    return raw


def read_columns(csv_path: str | Path) -> list[str]:
    """Header only — the catalog is derived from column names, never from rows."""
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        header = next(csv.reader(f))
    return [c.strip() for c in header]


def build_run_config() -> RunConfig:
    return RunConfig()


_LOAD_RULES = object()


def current_fingerprint(run_config: RunConfig | None = None, *, rules=_LOAD_RULES) -> dict:
    """The identity of the catalog this environment would produce right now.

    The builder and the server call the same function, which is what makes the
    staleness guard meaningful rather than decorative.
    """
    run_config = run_config or build_run_config()
    path = dataset_path()
    return catalog_fingerprint(
        cohort_file=path,
        columns=read_columns(path),
        outcome_col=outcome_column(),
        schema_version=cfg_mod.SCHEMA_VERSION,
        builder_version=cfg_mod.CATALOG_BUILD_VERSION,
        embedding_model=run_config.embedding.model,
        embedding_revision=run_config.embedding.revision,
        rules=load_rules() if rules is _LOAD_RULES else rules,
    )


def get_matcher() -> Matcher:
    # Re-read policy on each request so an edited policy cannot reuse a stale singleton.
    rules = load_rules()
    fingerprint = current_fingerprint(rules=rules)
    import fcntl
    # Coordinate with automatic builders so multi-file publication is never read
    # halfway through. Cached matchers remain valid for their own fingerprint.
    with (cfg_mod.CATALOG_JSON.parent / '.matcher.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_SH)
        return _get_matcher_cached(json.dumps(fingerprint, sort_keys=True),
                                   rules.model_dump_json() if rules is not None else None)


@lru_cache(maxsize=1)
def _get_matcher_cached(fingerprint_json, rules_json) -> Matcher:
    """Loaded once per process — the model (~420MB) and matrix cannot be re-read
    on every call."""
    from memstara.matcher.rules import RuleSet
    from memstara.matcher.catalog import meta_path
    rules = RuleSet.model_validate_json(rules_json) if rules_json is not None else None
    fingerprint = json.loads(fingerprint_json)
    # Legacy unstamped caches remain eligible only for policies with no exclusions.
    # An explicit empty policy cannot remove entries; activation verifies and stamps
    # the existing artifacts. Nonempty policies always require a matching stamp.
    metadata = meta_path(cfg_mod.CATALOG_JSON)
    if (rules is None or not rules.exclusions) and metadata.exists():
        if 'leakage_rules_sha1' not in json.loads(metadata.read_text()):
            fingerprint.pop('leakage_rules_sha1', None)
    run_config = build_run_config()
    matcher = VerifiedMatcher.from_catalog(
        cfg_mod.CATALOG_JSON,
        encoder=sentence_transformer_encoder(run_config.embedding),
        config=run_config,
        fingerprint=fingerprint,
    )
    # Runtime backstop. The builder excluding the outcome is a guarantee that holds
    # at build time; this is an invariant that must also hold for a catalog someone
    # hand-edited or copied in from another build.
    if rules is not None and any(e.feature_name in rules.excluded for e in matcher.entries):
        raise RuntimeError('Catalog contains study-excluded features; rebuild the matcher cache')
    outcome = outcome_column()
    if any(e.feature_name == outcome for e in matcher.entries):
        raise RuntimeError(
            f"{cfg_mod.CATALOG_JSON.name} contains the outcome column {outcome!r}. "
            "Refusing to serve it: the matcher would hand the label to an agent as a "
            "feature. Rebuild: `python scripts/build_matcher_cache.py`."
        )
    log.info(
        "matcher ready: %d entries, sim_threshold=%.2f, top_k=%d",
        len(matcher.entries),
        run_config.matcher.sim_threshold,
        run_config.matcher.top_k,
    )
    return matcher
