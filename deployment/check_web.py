"""Check the browser proxy using the configured public Host and Origin."""
import json
import os
import urllib.request
from urllib.parse import urlsplit


def check():
    origin = os.environ.get("MEMSTARA_PUBLIC_ORIGIN", "http://localhost:5173")
    headers = {"Host": urlsplit(origin).netloc, "Origin": origin}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    for path in ("/", "/control/health", "/control/pipelines", "/api/discovery/questions"):
        request = urllib.request.Request("http://web" + path, headers=headers)
        with opener.open(request, timeout=10) as response:
            data = response.read()
            if path == "/control/pipelines":
                if not isinstance(json.loads(data).get("pipelines"), list):
                    raise ValueError("Pipeline workspace response is invalid")
        print(f"OK {path}", flush=True)


if __name__ == "__main__":
    check()
