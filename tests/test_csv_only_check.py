import pytest
from memstara.dataset_upload import check_csv
from memstara.research_inputs import config


def test_csv_check_needs_only_file_and_preserves_source(tmp_path):
    path = tmp_path / 'heart.csv'
    raw = b'age,target,note\n,1,example\n55,0,NA\n'
    path.write_bytes(raw)
    result = check_csv({'dataset_path': str(path)})
    assert result['rows'] == 2
    assert result['columns_with_missing'] == {'age': 1, 'note': 1}
    assert result['missing_cells'] == 2
    assert result['nonnumeric_columns'] == ['note']
    assert path.read_bytes() == raw
    assert 'configuration' not in result
    assert 'execution_ready' not in result
    with pytest.raises(ValueError, match='knowledge_path is required'):
        config({'name': 'study', 'dataset_path': str(path)})


@pytest.mark.parametrize('raw', [b'', b'age,age\n1,2\n', b'age,target\n1\n', b'age\n\xff\n', b'age\n\0\n'])
def test_bad_csv_is_rejected_without_knowledge_requirements(tmp_path, raw):
    path = tmp_path / 'bad.csv'
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        check_csv({'dataset_path': str(path)})
    assert path.read_bytes() == raw


def test_clean_and_nonfinite_csv_reports(tmp_path):
    path = tmp_path / 'data.csv'
    path.write_text('x,y\n1,0\n2,1\n')
    assert check_csv({'dataset_path': str(path)})['missing_cells'] == 0
    path.write_text('x,y\ninf,0\n2,1\n')
    assert check_csv({'dataset_path': str(path)})['nonfinite_columns'] == ['x']


def test_binary_suggestions_only_cover_exact_observed_zero_one(tmp_path):
    path = tmp_path / 'data.csv'
    path.write_text('binary,constant,multiclass,text,spaces\n0,1,0,no, 0\n1,1,2,yes,1\n,1,1,no,1\n')
    result = check_csv({'dataset_path': str(path)})
    assert result['binary_columns'] == ['binary']
    assert result['setup_options']['preset'] is None


def test_heart_failure_preset_is_explicit_and_schema_specific():
    from memstara.dataset_upload import setup_options
    from memstara.heart_failure_demo import FEATURES, TARGET
    options = setup_options([*FEATURES, TARGET])
    assert options['preset']['target']['column'] == TARGET
    assert options['preset']['target']['positive_label'] == '1'
    assert 'not established' in options['preset']['target']['prediction_time']
    assert 'missing_policy' not in options['preset']
    assert setup_options(['age', 'target'])['preset'] is None
