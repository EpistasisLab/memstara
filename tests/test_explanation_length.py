from types import SimpleNamespace

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
