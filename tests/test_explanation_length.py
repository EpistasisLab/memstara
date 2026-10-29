from types import SimpleNamespace
import asyncio
from unittest.mock import AsyncMock

import pytest
from memstara.explanation_length import frozen_words, instruction, validate
from memstara.control.request import build_argv


@pytest.mark.parametrize('value', [0, -1, 10001, 2.5, True, None, '250'])
def test_invalid_report_length_rejected_at_request_boundary(value):
    with pytest.raises(ValueError, match='Explanation report length'):
        build_argv({'explanation_words': value}, [])


def test_target_is_advisory_and_resume_keeps_frozen_length():
    args = SimpleNamespace(explanation_words=600)
    assert frozen_words(SimpleNamespace()) == 250
    assert frozen_words(args) == 600
    assert frozen_words(args, {'explanation_words': 325}) == 325
    assert frozen_words(args, {}) is None
    assert instruction(None) == ''
    assert 'approximately 600 words' in instruction(validate(600))
    assert 'Do not truncate sentences' in instruction(600)
    assert 'structured records' in instruction(600)


def test_length_revision_preserves_complete_response_and_records_attempts():
    from memstara.explanation_length import refine
    revised = 'word ' * 250
    invoke = AsyncMock(return_value=(revised, {'status': 'completed', 'run_id': 'revision'}))
    text, entry = asyncio.run(refine('word ' * 154, {'run_id': 'original'}, 250, invoke))
    assert text == revised
    assert entry['explanation_length']['within_range']
    assert [a['actual_words'] for a in entry['explanation_length']['attempts']] == [154, 250]
    invoke.assert_awaited_once()


def test_length_revision_is_bounded_and_does_not_fail_for_length():
    from memstara.explanation_length import refine
    invoke = AsyncMock(return_value=('Brief report.', {'status': 'completed'}))
    text, entry = asyncio.run(refine('Initial report.', {'status': 'completed'}, 250, invoke))
    assert text == 'Brief report.'
    assert invoke.await_count == 2
    assert entry['status'] == 'completed'
    assert not entry['explanation_length']['within_range']


def test_legacy_and_in_range_reports_need_no_revision():
    from memstara.explanation_length import refine
    invoke = AsyncMock()
    for words, text in [(None, 'Historical report'), (100, 'word ' * 100)]:
        result, _ = asyncio.run(refine(text, {'status': 'completed'}, words, invoke))
        assert result == text
    invoke.assert_not_awaited()


def test_word_count_excludes_structured_fences_and_link_urls():
    from memstara.explanation_length import assessment
    assert assessment('One [reference](https://example.com/path) ```json\n{"a": 42}\n```', 2)[
        'actual_words'] == 2
