"""Check the browser proxy using the configured public Host and Origin."""
import json
import base64
import os
from pathlib import Path
from urllib.error import HTTPError
import urllib.request
from urllib.parse import urlsplit


def check_download_api(opener, headers, authorization):
    """Invalid format validates the deployed route without reading any study data."""
    path = '/api/experiments/linked-download?run_tags=readiness-probe&format=readiness-probe'
    request = urllib.request.Request('http://web' + path, headers=headers)
    try:
        with opener.open(request, timeout=10):
            raise ValueError('Download API authentication is not enforced')
    except HTTPError as error:
        error.close()
        if error.code != 401:
            raise ValueError('Download API authentication check failed') from None
    request.add_header('Authorization', authorization)
    try:
        with opener.open(request, timeout=10):
            raise ValueError('Download API did not reject the readiness probe')
    except HTTPError as error:
        try:
            body = json.loads(error.read())
        except (ValueError, TypeError):
            body = {}
        finally:
            error.close()
        errors = body.get('detail') if isinstance(body, dict) else None
        if error.code != 422 or not isinstance(errors, list) or not any(
            isinstance(item, dict) and item.get('loc') == ['query', 'format'] for item in errors
        ):
            raise ValueError('Native download API is unavailable. Rebuild both API and web services before using exports.') from None
    print('OK native linked-download API (no experiment or export started)', flush=True)


def check():
    origin = os.environ.get("MEMSTARA_PUBLIC_ORIGIN", "http://localhost:5173")
    headers = {"Host": urlsplit(origin).netloc, "Origin": origin}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    credentials = json.loads(Path("/run/secrets/memstara-web-auth.json").read_text())
    authorization = "Basic " + base64.b64encode(
        (credentials["username"] + ":" + credentials["password"]).encode()
    ).decode()
    for path in ("/", "/control/health", "/control/pipelines", "/api/discovery/questions"):
        request = urllib.request.Request("http://web" + path, headers=headers)
        try:
            with opener.open(request, timeout=10):
                raise ValueError("Web authentication is not enforced")
        except HTTPError as error:
            if error.code != 401:
                raise
        request.add_header("Authorization", authorization)
        with opener.open(request, timeout=10) as response:
            data = response.read()
            if path == "/control/pipelines":
                if not isinstance(json.loads(data).get("pipelines"), list):
                    raise ValueError("Pipeline workspace response is invalid")
        print(f"OK {path}", flush=True)
    check_download_api(opener, headers, authorization)


if __name__ == "__main__":
    check()
