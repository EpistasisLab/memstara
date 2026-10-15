"""Prepare semantic predictor indexes before pipeline readiness checks, for any CSV."""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time


def ensure(catalog: Path | None = None) -> dict:
    """Serialize builders and publish only a fully validated cache; never call an LLM."""
    import numpy as np
    from memstara.paths import output_dir
    from memstara.matcher.catalog import build_catalog, save_catalog, save_catalog_meta, meta_path, verify_catalog
    from memstara.matcher.embedder import (embed_catalog, save_embeddings, sentence_transformer_encoder,
                                          embeddings_path, embeddings_stamp_path, embeddings_stale)
    from memstara.matcher.service import (build_run_config, current_fingerprint, dataset_path,
                                          outcome_column, read_columns)
    from memstara.matcher.rules import load_rules
    from memstara.pipeline.checkpoint import atomic_json

    catalog = catalog or output_dir() / "matcher_catalog.json"
    catalog.parent.mkdir(parents=True, exist_ok=True)
    paths = (catalog, meta_path(catalog), embeddings_path(catalog), embeddings_stamp_path(catalog))
    stamp = catalog.with_suffix('.ready.json')
    def digest(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    with (catalog.parent / '.matcher.lock').open('a') as lock:
        started = time.monotonic()
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() - started > 600:
                    raise RuntimeError('Timed out waiting for another predictor-index preparation') from None
                time.sleep(.2)
        rules, run_config = load_rules(), build_run_config()
        expected = current_fingerprint(run_config, rules=rules)
        if stamp.is_file():
            try:
                receipt = json.loads(stamp.read_text())
                hashes = receipt.get('hashes') if isinstance(receipt, dict) else None
                if (isinstance(receipt, dict) and receipt.get('fingerprint') == expected
                        and isinstance(hashes, dict) and set(hashes) == {p.name for p in paths}
                        and all(p.is_file() and digest(p) == hashes[p.name] for p in paths)):
                    return {'status': 'ready', 'action': 'reused', 'catalog': str(catalog)}
            except (OSError, ValueError, TypeError):
                pass
        columns, outcome = read_columns(dataset_path()), outcome_column()
        if outcome not in columns:
            raise ValueError('Configured target is missing from the dataset; predictor index was not built')
        entries = build_catalog(columns, outcome_col=outcome, rules=rules)
        if not entries or any(entry.feature_name == outcome for entry in entries):
            raise ValueError('Predictor index has no eligible features or includes the target')
        texts = [entry.match_text for entry in entries]
        matrix = embed_catalog(texts, sentence_transformer_encoder(run_config.embedding))
        if matrix.ndim != 2 or matrix.shape[0] != len(entries) or not matrix.shape[1] or not np.isfinite(matrix).all():
            raise ValueError('Predictor embeddings are incomplete or non-finite')
        # A failed build leaves the previous cache untouched. The ready receipt is
        # published last, and readers share this lock during cache loading.
        with tempfile.TemporaryDirectory(prefix='.matcher-building-', dir=catalog.parent) as folder:
            staged = Path(folder) / catalog.name
            save_catalog(entries, staged)
            save_embeddings(matrix, staged, match_texts=texts, cfg=run_config.embedding)
            save_catalog_meta(entries, staged, expected)
            if (verify_catalog(staged, expected)
                    or embeddings_stale(staged, match_texts=texts, cfg=run_config.embedding)):
                raise ValueError('New predictor index failed validation')
            if current_fingerprint(run_config, rules=load_rules()) != expected:
                raise ValueError('Dataset or predictor policy changed during index preparation; '
                                 'restart with stable inputs')
            staged_paths = (staged, meta_path(staged), embeddings_path(staged), embeddings_stamp_path(staged))
            hashes = {p.name: digest(p) for p in staged_paths}
            for source, destination in zip(staged_paths, paths, strict=True):
                os.replace(source, destination)
            atomic_json(stamp, {'fingerprint': expected, 'hashes': hashes})
        return {'status': 'ready', 'action': 'built', 'catalog': str(catalog), 'predictors': len(entries)}
