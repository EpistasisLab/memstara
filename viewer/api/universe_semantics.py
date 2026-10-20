"""Local, versioned semantic question index. Never modifies experiment records."""
import fcntl
import hashlib
import json
import os
import threading
from pathlib import Path

MODEL = 'pritamdeka/S-PubMedBert-MS-MARCO'
REVISION = '96786c7024f95c5aac7f2b9a18086c7b97b23036'
_lock = threading.Lock()
_model = None


def encode(texts):
    global _model
    # Optional viewer extra; no remote inference or automatic model downloads.
    import torch
    from sentence_transformers import SentenceTransformer
    torch.set_num_threads(1)
    if _model is None:
        _model = SentenceTransformer(MODEL, revision=REVISION, device='cpu', local_files_only=True)
        _model.max_seq_length = 512
    return _model.encode(texts, batch_size=16, normalize_embeddings=True, show_progress_bar=False)


def fingerprint(text):
    return hashlib.sha256(text.encode()).hexdigest()


def index(rows, query='', question_id=None, encoder=None, directory=None, scope='all'):
    """Cosine neighbors are authoritative; fixed PCA is only a visual projection."""
    import numpy as np
    encoder = encoder or encode
    directory = Path(directory or os.environ.get('MEMSTARA_UNIVERSE_CACHE', '/tmp/memstara-universe'))
    if scope != 'all':
        directory = directory / hashlib.sha256(scope.encode()).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    identity = {'model': MODEL, 'revision': REVISION, 'input': 'question text; whitespace normalized',
                'projection': 'fixed PCA basis v1', 'metric': 'cosine similarity',
                'max_input_tokens': 512, 'long_text_policy': 'first 512 model tokens', 'numpy': np.__version__}
    path = directory / 'index.json'
    with _lock, (directory / 'index.lock').open('a') as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        saved = json.loads(path.read_text()) if path.exists() else {}
        if saved.get('identity') != identity:
            saved = {'identity': identity, 'records': {}}
        records = saved['records']
        current = {}
        pending = []
        for row in rows:
            text = ' '.join(row['text'].split())
            if not text:
                continue
            key = str(row['question_id'])
            old = records.get(key)
            if old and old['text_hash'] == fingerprint(text):
                current[key] = old
            else:
                pending.append((key, text))
        if pending:
            vectors = np.asarray(encoder([text for _, text in pending]), dtype=float)
            if vectors.ndim != 2 or len(vectors) != len(pending) or not np.isfinite(vectors).all():
                raise ValueError('Invalid question embeddings')
            for (key, text), vector in zip(pending, vectors, strict=True):
                norm = float(np.linalg.norm(vector))
                if norm <= 0:
                    raise ValueError('Empty question embedding')
                current[key] = {'text_hash': fingerprint(text), 'vector': (vector / norm).tolist()}
        if not current:
            # Clearing the universe also clears cached vectors and the old projection.
            path.unlink(missing_ok=True)
            return {'status': 'empty', 'indexed_count': 0, 'excluded_empty': len(rows),
                    'points': [], 'neighbors': [], 'identity': identity}
        keys = sorted(current, key=int)
        matrix = np.array([current[k]['vector'] for k in keys])
        if 'basis' not in saved:
            # Fix the basis and scale after the first build: new questions cannot move old points.
            center = matrix.mean(axis=0)
            _, _, basis = np.linalg.svd(matrix - center, full_matrices=False)
            basis = basis[:3]
            for row in basis:
                if row[np.argmax(np.abs(row))] < 0:
                    row *= -1
            saved['center'], saved['basis'] = center.tolist(), basis.tolist()
            saved['scale'] = max(float(np.linalg.norm((matrix-center) @ basis.T, axis=1).max()), .1)
        coords = (matrix - saved['center']) @ np.array(saved['basis']).T / saved['scale']
        coords = np.pad(coords, ((0, 0), (0, 3-coords.shape[1])))
        # Bound new points without moving already indexed points.
        coords /= np.maximum(np.linalg.norm(coords, axis=1, keepdims=True), 1)
        coords = np.round(coords, 12)
        reference = None
        if query.strip():
            reference = np.asarray(encoder([' '.join(query.split())])[0], dtype=float)
        elif question_id is not None and str(question_id) in current:
            reference = np.array(current[str(question_id)]['vector'])
        neighbors = []
        texts = {int(row['question_id']): row['text'] for row in rows}
        if reference is not None:
            norm = float(np.linalg.norm(reference))
            if not np.isfinite(reference).all() or norm <= 0:
                raise ValueError('Invalid search embedding')
            scores = matrix @ (reference/norm)
            order = sorted(range(len(keys)), key=lambda i: (-float(scores[i]), int(keys[i])))
            neighbors = [{'question_id': int(keys[i]), 'text': texts[int(keys[i])],
                          'similarity': float(np.clip(scores[i], -1, 1))}
                         for i in order if int(keys[i]) != question_id][:30]
        saved['records'] = current
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(saved))
        temp.replace(path)
        return {'status': 'ready', 'identity': identity,
                'index_hash': fingerprint(json.dumps(saved, sort_keys=True)),
                'indexed_count': len(current), 'excluded_empty': len(rows)-len(current),
                'points': [{'question_id': int(k), 'x': float(p[0]), 'y': float(p[1]), 'z': float(p[2])}
                           for k, p in zip(keys, coords, strict=True)],
                'neighbors': neighbors,
                'limitations': 'Screen distances are a distorted 3D projection; use cosine scores for similarity. '
                              'Similarity is not clinical validity, performance or novelty. '
                              'New entries keep the original projection basis.'}
