import json

from memstara.control.experiment_progress import summarize


def attempt(root, tag, start, end, final, parent=None):
    directory = root / tag
    directory.mkdir()
    config = {'run_tag': tag, 'pipeline_id': 'study', 'dataset_sha256': 'csv',
              'y_column': 'outcome', 'combination_plan': {'total_loops': 1200}, 'knowledge_hashes': {}}
    if parent:
        config['retry_selection'] = {'source_run_tag': parent, 'loops': list(range(start, 1201))}
    (directory / 'config.json').write_text(json.dumps(config))
    outcomes = {str(n): {'outcome': 'completed' if n < end else final} for n in range(start, end + 1)}
    (directory / 'iteration_outcomes.json').write_text(json.dumps(outcomes))
    return {'run_dir': str(directory)}


def test_continued_schedule_counts_retry_attempts_without_losing_completed_work(tmp_path):
    attempt(tmp_path, 'original', 1, 367, 'blocked')
    attempt(tmp_path, 'retry1', 367, 383, 'interrupted', 'original')
    head = attempt(tmp_path, 'retry2', 383, 413, 'running', 'retry1')
    # A separate fresh experiment sharing the pipeline must not inflate totals.
    attempt(tmp_path, 'fresh', 1, 100, 'completed')
    result = summarize(head)
    assert result['scheduled'] == 1200
    assert result['completed'] == 412
    assert result['started'] == 413
    assert result['attempts'] == 415
    assert result['retries'] == 2
    assert result['blocked'] == 0
    assert result['not_started'] == 787
    assert result['run_tags'] == ['original', 'retry1', 'retry2']


def test_broken_history_is_unknown_not_a_smaller_successful_total(tmp_path):
    head = attempt(tmp_path, 'retry', 367, 383, 'running', 'missing')
    assert summarize(head)['status'] == 'unavailable'
    assert 'completed' not in summarize(head)


def test_phantom_local_ordinals_are_not_additional_completed_work(tmp_path):
    attempt(tmp_path, 'original', 1, 367, 'blocked')
    head = attempt(tmp_path, 'retry', 367, 383, 'running', 'original')
    path = tmp_path / 'retry/iteration_outcomes.json'
    value = json.loads(path.read_text())
    value['1'] = {'outcome': 'completed'}
    path.write_text(json.dumps(value))
    assert summarize(head)['completed'] == 382
    assert summarize(head)['attempts'] == 384
