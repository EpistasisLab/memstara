"""Check the browser proxy using the configured public Host and Origin."""
import json
import base64
import os
from pathlib import Path
from urllib.error import HTTPError
import urllib.request
from urllib.parse import urlsplit


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


if __name__ == "__main__":
    check()
