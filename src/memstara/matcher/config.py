# SOURCE: SANDBOX-ORIGINAL — not copied from afc-forge.
#   The DEFAULT VALUES are upstream's, copied deliberately and cited at each
#   field (afc-forge `ade_forge/config.py:98-114`); the class definitions around
#   them are sandbox code. If a default here stops matching upstream's, this
#   matcher stops being comparable to afc-forge's — change one only on purpose.
"""Matcher settings — only the surface afc-forge `ade_forge/config.py` exposes.

The ported `matcher.py` reads exactly four values off a RunConfig:
    cfg.matcher.top_k         cfg.matcher.sim_threshold
    cfg.embedding.model       cfg.embedding.revision

afc-forge's RunConfig is 1,425 lines across 18 sub-configs and drags in yaml,
descriptors and leakage. All of that exists to produce those four values, so here
it collapses to three pydantic models — and it must be **pydantic, not a stdlib
dataclass**: the ported tests construct `RunConfig(matcher={"sim_threshold": 0.3,
"top_k": 5})`, passing sub-configs as dicts. Editing 20 tests to fit a dataclass
would leave tests that no longer prove identity with upstream.
"""

from __future__ import annotations

from typing import Final

from pydantic import BaseModel, ConfigDict, Field

from memstara.paths import output_dir


class _Base(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class MatcherConfig(_Base):
    """Values taken from afc-forge `config.py:98-114`.

    sim_threshold 0.88 was re-confirmed by measurement over EcoXAI's 1,393
    columns (scripts/calibrate_threshold.py, 2026-08-25). 21 concepts this cohort
    carries bottom out at top-1 0.918; 8 it does not carry top out at 0.915. The
    distributions overlap, so no floor separates present from absent — which is
    the finding, and the reason the agent contract is PICK-THE-GROUP rather than
    "take the top match above the threshold".

    0.88 is the highest floor that loses no real concept AND truncates no
    categorical family. Two independent walls sit just above it:
      * 0.90 cuts CAT__ALCOHOL_STATUS, whose weakest level scores 0.895. A
        truncated family is the one failure an agent cannot reword its way out
        of — it sees a family with a level missing and cannot tell.
      * 0.92 drops "low density lipoprotein cholesterol" and "antiretroviral
        therapy" outright.
    Going lower buys nothing: 0.86 lets in one more absent concept and takes the
    median group from 12 candidates to 65.
    """

    sim_threshold: float = Field(default=0.88, ge=0.0, le=1.0)
    top_k: int = Field(default=8, ge=1)
    max_match_retries: int = Field(default=2, ge=0)


class EmbeddingConfig(_Base):
    """The revision pin is part of the method — a run embedded by a model whose
    name is unchanged but whose weights were updated is not comparable to the run
    before it, and without a pin nobody can tell. The SHA below matches this
    machine's HF cache `main` ref, so pinning it is safe offline.
    """

    model: str = "pritamdeka/S-PubMedBert-MS-MARCO"
    revision: str | None = "96786c7024f95c5aac7f2b9a18086c7b97b23036"


class RunConfig(_Base):
    matcher: MatcherConfig = Field(default_factory=MatcherConfig)
    embedding: EmbeddingConfig = Field(default_factory=EmbeddingConfig)


# ---------------------------------------------------------------------------
# Catalog artifact paths
# ---------------------------------------------------------------------------
#: Bump when the shape of the meta (fingerprint) changes.
SCHEMA_VERSION: Final[int] = 1
#: Bump when `_parse_column` or a match_text template changes. The column list can
#: be untouched while the catalog means something different, and columns_sha1
#: cannot see that change.
CATALOG_BUILD_VERSION: Final[int] = 1

_OUTPUT_DIR = output_dir()

#: The only path setting. The other three artifacts are all derived from it
#: (embeddings_path / embeddings_stamp_path / meta_path). A second, independently
#: configured path constant is precisely the mechanism by which two files drift
#: out of agreement.
#:     matcher_catalog.json
#:       -> matcher_catalog.emb.npy    the matrix
#:       -> matcher_catalog.emb.json   the matrix's identity stamp
#:       -> matcher_catalog.meta.json  the catalog fingerprint
CATALOG_JSON = _OUTPUT_DIR / "matcher_catalog.json"
