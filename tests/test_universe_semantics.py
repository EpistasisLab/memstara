import importlib.util
from pathlib import Path
import numpy as np

spec = importlib.util.spec_from_file_location(
    'universe_semantics', Path(__file__).parents[1] / 'viewer/api/universe_semantics.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_neighbors_use_embeddings_and_new_records_keep_coordinates(tmp_path):
    vectors = {'heart': [1., 0., 0., 0.], 'cardiac': [.99, .01, 0., 0.],
               'infection': [0., 1., 0., 0.], 'renal': [0., 0., 1., 0.]}
    calls = []
    def encode(texts):
        calls.extend(texts)
        return np.array([vectors[t] for t in texts])
    rows = [{'question_id': i+1, 'text': t} for i, t in enumerate(vectors)]
    first = module.index(rows[:3], question_id=1, encoder=encode, directory=tmp_path)
    assert first['neighbors'][0]['question_id'] == 2
    calls.clear()
    second = module.index(rows, query='cardiac', encoder=encode, directory=tmp_path)
    assert second['points'][:3] == first['points']
    assert calls == ['renal', 'cardiac']
    assert second['neighbors'][0]['question_id'] == 2
    # Cleared records are removed from every neighbor search and persisted vectors.
    cleared = module.index(rows[1:], question_id=2, encoder=encode, directory=tmp_path)
    assert all(n['question_id'] != 1 for n in cleared['points'])


def test_empty_and_invalid_embeddings_are_explicit(tmp_path):
    import pytest
    empty = module.index([{'question_id': 1, 'text': ' '}], encoder=lambda t: [], directory=tmp_path)
    assert empty['status'] == 'empty'
    with pytest.raises(ValueError, match='Invalid'):
        module.index([{'question_id': 1, 'text': 'x'}], encoder=lambda t: [[float('nan')]], directory=tmp_path)


def test_cleared_universe_drops_cached_vectors_and_projection(tmp_path):
    module.index([{'question_id': 1, 'text': 'heart'}], encoder=lambda t: [[1., 0.]], directory=tmp_path)
    assert (tmp_path / 'index.json').exists()
    result = module.index([], directory=tmp_path)
    assert result['indexed_count'] == 0
    assert not (tmp_path / 'index.json').exists()
