from types import SimpleNamespace
from unittest.mock import Mock
from io import BytesIO
import pytest
pytest.importorskip("motoro", reason="Requires optional Motoro runtime; exercised in the full development suite")
from memstara.control import service


def handler(path, body):
    h = object.__new__(service.Handler)
    h.path = path
    h._refuse_stranger = lambda: False
    h._body = lambda: body
    h._send = Mock()
    return h


def test_key_requires_explicit_reveal():
    h = handler('/control/llm/key', {})
    h.do_POST()
    assert h._send.call_args.args[0] == 400


def test_foreign_origin_cannot_reveal_key():
    h = handler('/control/llm/key', {'reveal': True})
    h._refuse_stranger = lambda: True
    h.do_POST()
    h._send.assert_not_called()


def test_reveal_uses_only_selected_provider(monkeypatch):
    from memstara import config
    monkeypatch.setenv('MEMSTARA_LLM_PROVIDER', 'openai')
    monkeypatch.setenv('MEMSTARA_LLM_MODEL', 'test-model')
    monkeypatch.setattr(config, 'Settings', lambda: SimpleNamespace(openai_api_key='synthetic-openai', anthropic_api_key='synthetic-anthropic', anthropic_foundry_api_key='synthetic-foundry'))
    h = handler('/control/llm/key', {'reveal': True})
    h.do_POST()
    assert h._send.call_args.args == (200, {'api_key':'synthetic-openai'})


def test_key_responses_cannot_be_cached():
    h = object.__new__(service.Handler)
    h.send_response = Mock()
    h.send_header = Mock()
    h.end_headers = Mock()
    h.wfile = BytesIO()
    h._send(200, {'api_key':'synthetic-only'})
    h.send_header.assert_any_call('Cache-Control', 'no-store')
