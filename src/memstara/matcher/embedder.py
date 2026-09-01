# SOURCE: PORTED FROM afc-forge — NOT sandbox-authored code.
#   upstream: shared/afc-forge/ade_forge/tools/impl/embedder.py (312 lines)
# --- PORT NOTE (memstara) -------------------------------------
# A port of afc-forge `ade_forge/tools/impl/embedder.py`. Four differences:
#   1. the EmbeddingConfig import points at matcher_impl.config
#   2. the device-selection expression is extracted into current_device()
#      (the selection rule itself is unchanged)
#   3. the embedding stamp records "device"
#   4. a device mismatch warns; it does not refuse
# torch / sentence_transformers stay imported inside functions, as upstream.
#
# The prose below this banner is UPSTREAM'S OWN TEXT, kept verbatim — "FE_Demo2"
# and the "§6.x" citations are afc-forge's references to its own predecessor and
# design notes, not this sandbox's.
# -------------------------------------------------------------------------
"""The catalog encoder — lazy, pinned by revision, and injectable.

Ported from FE_Demo2 `tools/impl/embedder.py`. Three things change, and each is a
rule from the plan rather than a preference:

**Injectable.** The encoder is a `Callable[[Sequence[str]], np.ndarray]`, not an
import. Nothing in `matcher.py` reaches for a model — it is handed one. That is
what lets the whole matcher test suite run in CI with a deterministic fake and no
1.3 GB download, and it is also how a site swaps in its own encoder without
forking the matcher.

**Lazy.** `sentence_transformers` and `torch` are imported inside
`sentence_transformer_encoder()`, never at module import. `ade-forge validate` and
every prompt-render path stay importable on a machine that has never loaded the
model.

**Pinned by revision** (§6.1.2). The encoder is part of the *method*: same model
name, refreshed weights, same fingerprint is exactly the hole that would let
`ade-forge master` pool runs across a silent re-embedding. `embedding.revision`
unset is a loud warning at load time, never silent acceptance.

The HF-cache preference is ported as-is because the failure it fixes is real and
measured: loading without it fires ~25 revalidation requests at huggingface.co,
most of them 404 probes for optional files this model does not ship, costing ~4 s
(9.1 s online vs 5.0 s cached) and putting startup on the network's critical path.
An explicit `HF_HUB_OFFLINE` from the user always wins — that is the escape hatch
for deliberately refreshing the model.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Final

import numpy as np

from memstara.matcher.config import EmbeddingConfig

log = logging.getLogger(__name__)

#: Text in, `(n, d)` float32 L2-normalized out — so cosine is a dot product.
Encoder = Callable[[Sequence[str]], np.ndarray]

#: What must be in the HF cache before going offline is safe: the
#: sentence-transformers config pair, plus weights in EITHER serialization.
_REQUIRED_CACHED = ("config.json", "modules.json")
_CACHED_WEIGHTS = ("model.safetensors", "pytorch_model.bin")


def l2_normalize(vectors: np.ndarray) -> np.ndarray:
    """Row-normalize to unit length, leaving zero rows alone."""
    arr = np.asarray(vectors, dtype=np.float32)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    return (arr / np.where(norms == 0.0, 1.0, norms)).astype(np.float32)


def current_device() -> str:
    """Added by the port. Upstream inlines this expression; it is a function here
    only so the stamp can record which device encoded the matrix. The selection
    rule is unchanged."""
    try:
        import torch
    except Exception:
        return "unknown"
    if torch.backends.mps.is_available():
        return "mps"
    return "cuda" if torch.cuda.is_available() else "cpu"


def _model_is_cached(model: str) -> bool:
    try:
        from huggingface_hub import try_to_load_from_cache
    except Exception:  # hub absent or renamed -> stay online
        return False

    def have(fname: str) -> bool:
        try:
            return isinstance(try_to_load_from_cache(model, fname), str)
        except Exception:
            return False

    return all(have(f) for f in _REQUIRED_CACHED) and any(have(f) for f in _CACHED_WEIGHTS)


def _prefer_cached_model(model: str) -> bool:
    """Serve from the local HF cache when it is already complete. Ported.

    Returns True if this call flipped the flag, so the caller can undo it when the
    cache turns out to be partial.
    """
    if os.environ.get("HF_HUB_OFFLINE") is not None:
        return False  # the user made the call; do not second-guess it
    if not _model_is_cached(model):
        return False  # cold cache: let it download

    os.environ["HF_HUB_OFFLINE"] = "1"  # for child processes and later imports
    try:  # ...and for an already-imported hub
        from huggingface_hub import constants

        constants.HF_HUB_OFFLINE = True  # is_offline_mode() reads this at call time
    except Exception:
        pass
    return True


def _restore_online() -> None:
    os.environ.pop("HF_HUB_OFFLINE", None)
    try:
        from huggingface_hub import constants

        constants.HF_HUB_OFFLINE = False
    except Exception:
        pass


def load_sentence_transformer(config: EmbeddingConfig | None = None):  # noqa: ANN201
    """Load the pinned SentenceTransformer. Imports the heavy stack HERE, not above."""
    cfg = config or EmbeddingConfig()
    if cfg.revision is None:
        log.warning(
            "embedding.revision is unset for %s, so this run pins the model by NAME only. "
            "The weights behind a name can change; runs embedded before and after such a "
            "refresh are not poolable and nothing downstream can tell them apart. "
            "Pin a revision before any run whose features you intend to compare.",
            cfg.model,
        )

    # Flip to cache-only BEFORE importing sentence_transformers: transformers
    # snapshots the offline flag at import time.
    went_offline = _prefer_cached_model(cfg.model)

    import torch
    from sentence_transformers import SentenceTransformer

    device = current_device()
    kwargs = {"device": device}
    if cfg.revision is not None:
        kwargs["revision"] = cfg.revision
    try:
        return SentenceTransformer(cfg.model, **kwargs)
    except Exception:
        if not went_offline:
            raise
        # The cache looked complete and was not (partial or corrupt) -> retry online.
        _restore_online()
        return SentenceTransformer(cfg.model, **kwargs)


def sentence_transformer_encoder(
    config: EmbeddingConfig | None = None, *, batch_size: int = 128
) -> Encoder:
    """The production encoder, loaded on first call and held for the process."""
    cfg = config or EmbeddingConfig()
    model_holder: list[object] = []

    def encode(texts: Sequence[str]) -> np.ndarray:
        if not model_holder:
            model_holder.append(load_sentence_transformer(cfg))
        model = model_holder[0]
        if not texts:
            dim = model.get_sentence_embedding_dimension()  # type: ignore[attr-defined]
            return np.zeros((0, dim), dtype=np.float32)
        out = model.encode(  # type: ignore[attr-defined]
            list(texts),
            batch_size=batch_size,
            convert_to_numpy=True,
            normalize_embeddings=True,  # cosine == dot
            show_progress_bar=False,
        )
        return np.asarray(out, dtype=np.float32)

    return encode


# ---------------------------------------------------------------------------
# The cached catalog matrix
# ---------------------------------------------------------------------------
def embed_catalog(match_texts: Sequence[str], encoder: Encoder, *, chunk: int = 512) -> np.ndarray:
    """Embed every catalog `match_text` into an `(n, d)` L2-normalized matrix.

    Chunked so a large catalog does not depend on the encoder's own batching, and
    re-normalized here rather than trusted: a substituted encoder that returns
    unnormalized vectors would otherwise turn every cosine into a dot product of
    arbitrary magnitude, and the similarity floor would quietly stop meaning
    anything.
    """
    texts = list(match_texts)
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    blocks = [np.asarray(encoder(texts[i : i + chunk])) for i in range(0, len(texts), chunk)]
    return l2_normalize(np.vstack(blocks))


#: Bumped when the stamp's own shape changes. An unreadable or older stamp reads
#: as "cannot prove identity" and costs one re-embed, never a silent reuse.
STAMP_SCHEMA_VERSION: Final[int] = 1


def embeddings_path(catalog_json: str | Path) -> Path:
    p = Path(catalog_json)
    return p.parent / f"{p.stem}.emb.npy"


def embeddings_stamp_path(catalog_json: str | Path) -> Path:
    """Where the matrix's identity lives — beside it, never inside the `.npy`."""
    p = Path(catalog_json)
    return p.parent / f"{p.stem}.emb.json"


def match_text_digest(match_texts: Sequence[str]) -> str:
    """What a cached matrix embedded: sha1 over the ORDERED `match_text`s.

    Keyed on the texts rather than on the catalog's own fingerprint, and the
    difference is not cosmetic: the fingerprint moves whenever the descriptor
    *schema* gains a field (Phase 4 did exactly that), which would force a re-embed
    of a matrix that is provably identical. It also misses the case that matters —
    a rebuild that rewords a `match_text` without changing the entry count.

    JSON-encoded rather than newline-joined: a `match_text` may itself contain a
    newline, and a delimiter that can appear in the data makes two different
    catalogs hash alike.
    """
    payload = json.dumps(list(match_texts), ensure_ascii=False)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def save_embeddings(
    matrix: np.ndarray,
    catalog_json: str | Path,
    *,
    match_texts: Sequence[str],
    cfg: EmbeddingConfig | None = None,
) -> Path:
    """Write the matrix and, beside it, the identity of what it embedded.

    `match_texts` is required rather than optional: a matrix saved without saying
    what it is of cannot be checked later, and an unstamped cache is exactly the
    artifact this guard exists to stop being reused.
    """
    path = embeddings_path(catalog_json)
    path.parent.mkdir(parents=True, exist_ok=True)
    arr = np.asarray(matrix, dtype=np.float32)
    np.save(path, arr)
    cfg = cfg or EmbeddingConfig()
    embeddings_stamp_path(catalog_json).write_text(
        json.dumps(
            {
                "schema_version": STAMP_SCHEMA_VERSION,
                "match_text_sha1": match_text_digest(match_texts),
                "n": int(arr.shape[0]),
                "model": cfg.model,
                "revision": cfg.revision,
                "device": current_device(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def embeddings_stale(
    catalog_json: str | Path,
    *,
    match_texts: Sequence[str],
    cfg: EmbeddingConfig | None = None,
) -> str | None:
    """Why the cached matrix cannot be reused, or `None` if it can.

    The row count is not enough on its own — a rebuild that rewords a `match_text`
    leaves it unchanged, and the matcher then answers every concept against vectors
    for text the catalog no longer contains. Nothing crashes; the matches are just
    quietly wrong, which is the whole failure mode.

    `cfg` unset skips the encoder comparison and checks only the texts. That is for
    the caller that has no `EmbeddingConfig` to hand: comparing against defaults
    would report a stale matrix on a catalog that is fine.
    """
    if not embeddings_path(catalog_json).exists():
        return "no cached embedding matrix beside the catalog"
    stamp_path = embeddings_stamp_path(catalog_json)
    if not stamp_path.exists():
        return "the cached embedding matrix carries no identity stamp"
    try:
        stamp = json.loads(stamp_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return f"the embedding stamp is unreadable ({stamp_path.name})"
    if stamp.get("schema_version") != STAMP_SCHEMA_VERSION:
        return (
            f"the embedding stamp is version {stamp.get('schema_version')!r}, "
            f"this build writes {STAMP_SCHEMA_VERSION}"
        )
    texts = list(match_texts)
    if stamp.get("n") != len(texts):
        return f"the catalog has {len(texts)} entries, the cached matrix has {stamp.get('n')}"
    if stamp.get("match_text_sha1") != match_text_digest(texts):
        return "the catalog's match texts changed since the matrix was embedded"
    if cfg is not None and (stamp.get("model"), stamp.get("revision")) != (cfg.model, cfg.revision):
        return (
            f"the matrix was embedded by {stamp.get('model')}@{stamp.get('revision')}, "
            f"this run uses {cfg.model}@{cfg.revision}"
        )
    # Added by the port. Building on MPS and serving on CPU shifts cosines by
    # ~1e-3, which can flip a candidate sitting on the 0.88 floor. That is not a
    # large enough difference to force a re-embed, so this warns rather than refuses.
    stamped_device = stamp.get("device")
    now = current_device()
    if stamped_device not in (None, "unknown", now):
        log.warning(
            "the catalog matrix was embedded on %s and this process encodes queries on %s. "
            "Cosines shift by ~1e-3 across devices, which can flip a candidate across the "
            "similarity floor. Rebuild the cache on this device if borderline matches matter.",
            stamped_device,
            now,
        )
    return None


def load_embeddings(catalog_json: str | Path) -> np.ndarray:
    """Load the cached matrix. Call `embeddings_stale` first — this does not check.

    Split that way because the check has two answers depending on who asks:
    `build-catalog` and `embed-catalog` re-embed a stale matrix, and every other
    caller refuses one. A loader that decided for them would have to pick one, and
    the only picks on offer are "embed inside a run" and "crash".
    """
    return np.load(embeddings_path(catalog_json)).astype(np.float32)
