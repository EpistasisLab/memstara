"""Exercise the actual Nginx authentication boundary without Docker or model calls."""
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import runpy
import shutil
import socket
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, ProxyHandler

import pytest


def test_nginx_protects_pages_assets_and_backends(tmp_path):
    nginx = shutil.which("nginx")
    if not nginx:
        pytest.skip("Local nginx is needed for this integration test")
    root = Path(__file__).resolve().parents[1]
    setup = runpy.run_path(str(root / "deployment/setup-web-auth.py"))
    credentials = tmp_path / "auth"
    setup["configure"]("fixture", "fixture-password", credentials)
    assert "fixture-password" not in (credentials / "htpasswd").read_text()
    assert (credentials / "client.json").stat().st_mode & 0o777 == 0o600
    assert json.loads((credentials / "client.json").read_text())["username"] == "fixture"

    class Backend(BaseHTTPRequestHandler):
        def do_GET(self):
            assert self.headers.get("Authorization") is None
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"pipelines": []}')

        def log_message(self, *args):
            pass

    backend = ThreadingHTTPServer(("127.0.0.1", 0), Backend)
    worker = threading.Thread(target=backend.serve_forever, daemon=True)
    worker.start()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    (tmp_path / "index.html").write_text("fixture UI")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets/app.js").write_text("fixture asset")
    config = (root / "deployment/nginx.conf").read_text()
    config = config.replace("listen 80;", f"listen 127.0.0.1:{port};")
    config = config.replace("/usr/share/nginx/html", str(tmp_path))
    config = config.replace("/etc/nginx/memstara.htpasswd", str(credentials / "htpasswd"))
    for upstream in ("api:8000", "control:8072"):
        config = config.replace(upstream, f"127.0.0.1:{backend.server_port}")
    path = tmp_path / "nginx.conf"
    path.write_text(f"daemon off; master_process off; pid {tmp_path}/nginx.pid; "
                    f"error_log {tmp_path}/error.log; events {{}} http {{ access_log off; {config} }}")
    process = subprocess.Popen([nginx, "-p", str(tmp_path), "-c", str(path)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    opener = build_opener(ProxyHandler({}))

    def get(route, password=None):
        headers = {}
        if password is not None:
            headers["Authorization"] = "Basic " + base64.b64encode(f"fixture:{password}".encode()).decode()
        return opener.open(Request(f"http://127.0.0.1:{port}" + route, headers=headers), timeout=3)

    try:
        for _ in range(50):
            if process.poll() is not None:
                pytest.fail(process.stderr.read().decode())
            try:
                get("/")
            except HTTPError:
                break
            except URLError:
                time.sleep(0.05)
        for route in ("/", "/results", "/assets/app.js", "/control/health", "/control/pipelines",
                      "/api/discovery/questions"):
            for password in (None, "incorrect"):
                with pytest.raises(HTTPError) as caught:
                    get(route, password)
                assert caught.value.code == 401
                assert 'Basic realm="Memstara"' in caught.value.headers["WWW-Authenticate"]
            with get(route, "fixture-password") as response:
                assert response.status == 200
    finally:
        process.terminate()
        process.wait(timeout=5)
        backend.shutdown()
        backend.server_close()
        worker.join(timeout=5)
