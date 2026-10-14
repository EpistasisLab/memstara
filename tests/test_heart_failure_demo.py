"""Demo preparation is explicit, non-imputing and preserves original data."""
import csv
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'demo', Path(__file__).resolve().parents[1] / 'scripts/prepare_heart_failure_demo.py')
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def fixture(tmp_path, invalid=False):
    source = tmp_path / 'source.csv'
    with source.open('w', newline='') as f:
        w = csv.writer(f)
        w.writerow([*demo.FEATURES, demo.TARGET])
        w.writerow(['1'] * 8 + ['0'])
        w.writerow(['2'] * 8 + ['1'])
        w.writerow(['?'] + ['3'] * 7 + ['unknown' if invalid else '0'])
    corpus = tmp_path / 'okf'
    corpus.mkdir()
    (corpus / 'index.md').write_text('Synthetic fixture')
    return source, corpus


def test_complete_cases_preserve_source_and_record_selection(tmp_path):
    source, corpus = fixture(tmp_path)
    original = source.read_bytes()
    destination = tmp_path / 'derived'
    result = demo.prepare(source, corpus, destination)
    assert (result['source_rows'], result['retained_rows'], result['excluded_rows']) == (3, 2, 1)
    assert source.read_bytes() == original
    assert '?' not in (destination / 'dataset.csv').read_text()
    assert json.loads((destination / 'research.json').read_text())['missing_policy'] == 'reject'
    with pytest.raises(ValueError, match='Destination exists'):
        demo.prepare(source, corpus, destination)


def test_invalid_target_is_not_silently_dropped(tmp_path):
    source, corpus = fixture(tmp_path, invalid=True)
    with pytest.raises(ValueError, match='Target labels'):
        demo.prepare(source, corpus, tmp_path / 'derived')
    assert not (tmp_path / 'derived').exists()
