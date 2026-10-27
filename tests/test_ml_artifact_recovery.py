"""Recovery accepts intact receipts, never missing or partially written model files."""
import hashlib
import json

import pytest

from memstara.ml_artifact_recovery import verify_result


@pytest.fixture
def receipt(tmp_path):
    bundle = tmp_path / 'model'
    bundle.mkdir()
    artifact = bundle / 'model-0.joblib'
    artifact.write_bytes(b'synthetic artifact; never unpickled')
    manifest = bundle / 'manifest.json'
    manifest.write_text(json.dumps({'version': 1, 'files': {
        artifact.name: hashlib.sha256(artifact.read_bytes()).hexdigest()}}))
    result = {'evaluation': {'reproducibility': {'bundle_path': str(bundle),
              'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest()}}}
    return result, bundle


def test_intact_saved_fit_is_read_only(receipt, tmp_path):
    result, bundle = receipt
    before = {p.name: p.read_bytes() for p in bundle.iterdir()}
    verify_result(result, tmp_path)
    assert before == {p.name: p.read_bytes() for p in bundle.iterdir()}


@pytest.mark.parametrize('damage', ['model_missing', 'model_changed', 'manifest_changed', 'outside_root'])
def test_partial_or_modified_artifacts_are_not_reused(receipt, tmp_path, damage):
    result, bundle = receipt
    if damage == 'model_missing':
        (bundle / 'model-0.joblib').unlink()
    elif damage == 'model_changed':
        (bundle / 'model-0.joblib').write_bytes(b'partial')
    elif damage == 'manifest_changed':
        (bundle / 'manifest.json').write_text('{}')
    with pytest.raises(ValueError, match='refusing reuse'):
        verify_result(result, tmp_path / 'different' if damage == 'outside_root' else tmp_path)


def test_failed_or_unverifiable_results_do_not_authorize_retraining(tmp_path):
    for result in ({'status': 'failed'}, {'model': 'logistic_regression'}):
        with pytest.raises(ValueError):
            verify_result(result, tmp_path)
