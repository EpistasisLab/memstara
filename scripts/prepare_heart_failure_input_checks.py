"""Create manual upload test cases without changing the bundled source CSV."""
import csv
import hashlib
import json
from pathlib import Path

from memstara.heart_failure_demo import FEATURES, TARGET
from memstara.research_inputs import MISSING


def prepare(source: Path, destination: Path):
    original = source.read_bytes()
    destination.mkdir(parents=True, exist_ok=False)
    columns = [*FEATURES, TARGET]
    with source.open(newline='', encoding='utf-8-sig') as stream:
        rows = [{key: row[key] for key in columns} for row in csv.DictReader(stream)
                if all(row[key].strip().lower() not in MISSING for key in columns)]
    if len(rows) < 10:
        raise ValueError('Insufficient complete rows for manual test cases')
    cases = [
        ('01_complete_numeric', [], 'PASS', 'Complete-case baseline; eight numeric predictors.'),
        ('02_one_missing_predictor', [(0, FEATURES[0], '')], 'BLOCK', 'One blank predictor cell.'),
        ('03_missing_target', [(0, TARGET, '')], 'BLOCK', 'One blank target label.'),
        ('04_multiple_missing_columns', [(i, FEATURES[i], '') for i in range(4)], 'BLOCK', 'Blanks in four predictor columns.'),
        ('05_entire_column_missing', [(i, FEATURES[1], '') for i in range(len(rows))], 'BLOCK', 'A predictor column is entirely empty.'),
        ('06_missing_tokens', [(i, FEATURES[0], value) for i, value in enumerate(['NA', 'NaN', 'null', '?'])], 'BLOCK', 'Explicit missing-value tokens.'),
        ('07_whitespace_missing', [(0, FEATURES[0], '   ')], 'BLOCK', 'Whitespace-only predictor value.'),
        ('08_infinite_predictor', [(0, FEATURES[0], 'inf')], 'BLOCK', 'Non-finite numeric predictor.'),
        ('09_text_predictor', [(0, FEATURES[0], 'not_numeric')], 'BLOCK', 'Text in a numeric predictor; no automatic encoding.'),
        ('10_unmapped_target', [(0, TARGET, 'unknown')], 'BLOCK', 'Target label outside the explicit 0/1 mapping.'),
    ]
    manifest = {'source': 'examples/heart-failure/dataset.csv', 'source_sha256': hashlib.sha256(original).hexdigest(),
                'target': TARGET, 'positive_label': '1', 'negative_label': '0', 'rows': len(rows),
                'preparation': 'Manual fixtures only: eight fixed predictors and complete rows selected before injecting defects. No source values changed.', 'cases': []}
    for name, changes, expected, description in cases:
        copy = [dict(row) for row in rows]
        for index, column, value in changes:
            copy[index][column] = value
        path = destination / f'{name}.csv'
        with path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=columns)
            writer.writeheader()
            writer.writerows(copy)
        manifest['cases'].append({'file': path.name, 'expected': expected, 'description': description,
                                  'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    assert source.read_bytes() == original
    (destination / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    (destination / 'README.txt').write_text(
        'HeartFailure manual CSV upload checks\n\nTarget: ' + TARGET + '\nPositive label: 1; negative label: 0. Use the bundled HeartFailure OKF.\n'
        'Upload each CSV in Add pipeline. Inspect inputs before attempting execution. BLOCK cases must not start model calls.\n'
        'Do not exclude defective columns to bypass checks. The complete baseline is a derived software demonstration, not a new clinical dataset.\n\n'
        + '\n'.join(f"{c['file']} — {c['expected']}: {c['description']}" for c in manifest['cases']) + '\n')
    return manifest


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(Path('examples/heart-failure/dataset.csv'), args.destination)
    print(f"Created {len(result['cases'])} CSV files in {args.destination}; source unchanged.")
