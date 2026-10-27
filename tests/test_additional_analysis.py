"""Additional analysis must use the approved count without resetting saved settings."""
import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from memstara.control.workspace import PipelineWorkspace, loop_totals


class Manager:
    def __init__(self, key):
        self.live = None
        self.history = [{"run_tag": "previous", "run_dir": "/unused"}]

    def running(self):
        return self.live

    def finished(self):
        return self.history


def workspace(tmp_path):
    w = PipelineWorkspace(tmp_path / "workspace.json", Manager)
    p = w.mutate({"action": "add", "configuration": {"waves": 10}})
    return w, p


def test_only_approved_extra_loops_and_saved_settings_unchanged(tmp_path):
    w, p = workspace(tmp_path)
    args = w.start(p['id'], lambda manager, item: item, mode='additional',
                   additional_loops=5, expected_run_tag='previous')
    assert args['configuration']['waves'] == 5
    assert args['configuration']['continuous'] is False
    assert w.items[0]['configuration']['waves'] == 10
    assert PipelineWorkspace(w.path, Manager).items[0]['configuration']['waves'] == 10


@pytest.mark.parametrize('count', [0, -1, 11, True, 1.5, '5', None])
def test_invalid_extra_budget_rejected(tmp_path, count):
    w, p = workspace(tmp_path)
    with pytest.raises(ValueError, match='Additional total replicates'):
        w.start(p['id'], lambda *_: pytest.fail('Launched'), mode='additional',
                additional_loops=count, expected_run_tag='previous')


def test_repeat_start_requires_explicit_intent_and_fresh_history(tmp_path):
    w, p = workspace(tmp_path)
    with pytest.raises(ValueError, match='Choose additional'):
        w.start(p['id'], lambda *_: pytest.fail('Launched'))
    with pytest.raises(ValueError, match='history changed'):
        w.start(p['id'], lambda *_: pytest.fail('Launched'), mode='additional',
                additional_loops=5, expected_run_tag='outdated')
    assert w.start(p['id'], lambda _, item: item['configuration']['waves'],
                   mode='fresh', expected_run_tag='previous') == 10


def test_two_tabs_cannot_launch_two_additions(tmp_path):
    w, p = workspace(tmp_path)
    def launch(manager, _):
        manager.live = {'run_tag': 'new'}
        return 'started'
    def start(_):
        try:
            return w.start(p['id'], launch, mode='additional', additional_loops=5,
                           expected_run_tag='previous')
        except ValueError:
            return 'blocked'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(start, range(2))) == ['blocked', 'started']


def test_totals_count_attempts_not_budgets_and_flag_missing_records(tmp_path):
    records = []
    for i in range(12):
        directory = tmp_path / str(i)
        directory.mkdir()
        (directory/'progress.json').write_text(json.dumps({'exploration':
            {'attempted': 5, 'completed': 4, 'blocked': 1}}))
        records.append({'run_tag':str(i), 'run_dir':str(directory)})
    records += [records[0], {'run_tag':'unknown','run_dir':str(tmp_path/'missing')}]
    assert loop_totals(records) == {'attempted':60,'completed':48,'blocked':12,'unknown_executions':1}
