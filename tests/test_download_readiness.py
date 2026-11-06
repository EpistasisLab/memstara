"""A deployment must not report ready with a missing/old download API."""
from io import BytesIO
import json
from pathlib import Path
import runpy
from urllib.error import HTTPError

import pytest

check = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'deployment/check_web.py'))['check_download_api']


class Opener:
    def __init__(self, status=422, body=None):
        self.requests = []
        self.status = status
        self.body = body if body is not None else {'detail': [{'loc': ['query', 'format'], 'type': 'literal_error'}]}

    def open(self, request, timeout):
        self.requests.append(request.get_header('Authorization'))
        assert timeout == 10
        status = 401 if len(self.requests) == 1 else self.status
        if status == 200:
            return BytesIO(b'{}')
        raise HTTPError(request.full_url, status, 'synthetic', {}, BytesIO(json.dumps(self.body).encode()))


def test_native_route_probe_checks_auth_and_schema_without_a_real_export():
    opener = Opener()
    check(opener, {}, 'Basic synthetic')
    assert opener.requests == [None, 'Basic synthetic']


@pytest.mark.parametrize('status,body', [(404, {'detail': 'Not Found'}), (503, {}),
    (422, {'detail': [{'loc': ['query', 'another_field']}]}), (200, {})])
def test_old_api_or_substitute_success_cannot_pass_readiness(status, body):
    with pytest.raises(ValueError):
        check(Opener(status, body), {}, 'Basic synthetic')
