"""Exercise the real HTTP guard without loading model or database dependencies."""
import ast
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from memstara.control.access import public_viewer


source = Path(__file__).resolve().parents[1] / "src/memstara/control/service.py"
tree = ast.parse(source.read_text())
guard = next(node for node in ast.walk(tree)
             if isinstance(node, ast.FunctionDef) and node.name == "_refuse_stranger")
namespace = {"os": os}
for node in tree.body:
    if isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id in {"_ALLOWED_HOSTS", "_ALLOWED_ORIGINS"}
        for target in node.targets
    ):
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), "exec"), namespace)
exec(compile(ast.Module(body=[guard], type_ignores=[]), str(source), "exec"), namespace)


class Handler:
    _refuse_stranger = namespace["_refuse_stranger"]

    def _send(self, status, payload):
        self.status = status


class PublicViewerTests(unittest.TestCase):
    def check_request(self, host, origin, public="http://10.226.8.205:8070"):
        handler = Handler()
        handler.headers = {"Host": host}
        if origin is not None:
            handler.headers["Origin"] = origin
        with patch.dict(os.environ, {"MEMSTARA_PUBLIC_ORIGIN": public}):
            return handler._refuse_stranger()

    def test_network_browser_get_and_post(self):
        for host in ("10.226.8.205", "10.226.8.205:8070"):
            for origin in (None, "http://10.226.8.205:8070"):
                self.assertFalse(self.check_request(host, origin))

    def test_untrusted_hosts_and_origins_remain_blocked(self):
        self.assertTrue(self.check_request("attacker.example", None))
        self.assertTrue(self.check_request("10.226.8.205", "http://attacker.example"))
        self.assertTrue(self.check_request("10.226.8.205", "http://10.226.8.205:9999"))
        self.assertTrue(self.check_request("10.226.8.205", None, public=""))

    def test_local_health_checks(self):
        self.assertFalse(self.check_request("127.0.0.1:8072", None))
        self.assertFalse(self.check_request("[::1]:8072", None))

    def test_invalid_configuration_fails_closed(self):
        for origin in ("*", "http://user:password@host", "http://host/path", "http://host:bad"):
            with self.assertRaises(ValueError):
                public_viewer(origin)
            self.assertTrue(self.check_request("localhost", None, public=origin))


if __name__ == "__main__":
    unittest.main()
