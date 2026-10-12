"""Verify wheel metadata, importable version and packaged prompt resources."""

from pathlib import Path
import json
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    wheels = list((ROOT / "dist").glob("*.whl"))
    if len(wheels) != 1:
        raise SystemExit("Expected exactly one freshly built wheel in dist/")
    wheel = wheels[0]
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        for source, packaged in (
            ("THIRD_PARTY_NOTICES.md", "memstara/third_party/THIRD_PARTY_NOTICES.md"),
            ("licenses/afc-forge-LICENSE.txt", "memstara/third_party/licenses/afc-forge-LICENSE.txt"),
        ):
            assert packaged in names, f"Missing third-party notice: {packaged}"
            assert archive.read(packaged) == (ROOT / source).read_bytes(), packaged
        for directory in ("prompts", "playbooks"):
            for path in (ROOT / "src/memstara" / directory).rglob("*.md"):
                # Local ignored notes are not required package resources.
                tracked = subprocess.run(
                    ["git", "ls-files", "--error-unmatch", str(path)], cwd=ROOT, capture_output=True
                )
                if tracked.returncode == 0:
                    name = path.relative_to(ROOT / "src").as_posix()
                    assert name in names, name
                    assert archive.read(name) == path.read_bytes(), name
        assert not any(
            part in {".env", "docs", "daily_log", "BACKLOG.md", "CLAUDE.md", "CHECKLIST.md"}
            for name in names
            for part in Path(name).parts
        )
    code = """import sys, json
sys.path.insert(0, sys.argv[1])
import memstara
from importlib.metadata import version
assert memstara.__version__ == version('memstara')
assert memstara.__version__ != '0.0.0+unknown'
print(json.dumps({'version':memstara.__version__, 'module':memstara.__file__}))
"""
    output = subprocess.check_output([sys.executable, "-I", "-c", code, str(wheel)], text=True)
    result = json.loads(output)
    assert str(wheel) in result["module"]
    print("Wheel resources and installed metadata agree:", result["version"])


if __name__ == "__main__":
    main()
