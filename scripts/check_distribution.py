"""Verify wheel metadata, importable version and packaged prompt resources."""

from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
import venv
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist-dir", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    wheels = list(args.dist_dir.resolve().glob("*.whl"))
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
        # The current specialist bundle is required even without sibling folders.
        bundle = ROOT / "src/memstara/resources/contributed"
        manifest = json.loads((bundle / "manifest.json").read_text())
        for relative in ["manifest.json", *[row["path"] for row in manifest["files"]]]:
            path = bundle / relative
            name = path.relative_to(ROOT / "src").as_posix()
            assert name in names, f"Missing portable skill resource: {name}"
            assert archive.read(name) == path.read_bytes(), name
        assert not any(
            part in {".env", "docs", "daily_log", "BACKLOG.md", "CLAUDE.md", "CHECKLIST.md"}
            for name in names
            for part in Path(name).parts
        )
    # Install the artifact rather than relying on zipimport or the editable checkout.
    with tempfile.TemporaryDirectory(prefix="memstara-wheel-smoke-") as temporary:
        root = Path(temporary)
        environment = root / "environment"
        venv.EnvBuilder(with_pip=True).create(environment)
        python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
        subprocess.run(
            [str(python), "-I", "-m", "pip", "install", "--no-index", "--no-deps",
             "--disable-pip-version-check", str(wheel)],
            cwd=root, check=True, capture_output=True, text=True,
        )
        with zipfile.ZipFile(wheel) as archive:
            expected = {name.removeprefix("memstara/"): hashlib.sha256(archive.read(name)).hexdigest()
                        for name in archive.namelist() if name.startswith("memstara/")
                        and not name.endswith("/")}
        manifest = root / "manifest.json"
        manifest.write_text(json.dumps(expected))
        code = """import sys, json, hashlib
from pathlib import Path
from importlib.metadata import version
from importlib.resources import files
import memstara
assert sys.prefix != sys.base_prefix
assert memstara.__version__ == version('memstara')
assert memstara.__version__ != '0.0.0+unknown'
module = Path(memstara.__file__).resolve()
assert module.is_relative_to(Path(sys.prefix).resolve()), module
package = files('memstara')
expected = json.loads(Path(sys.argv[1]).read_text())
for name, digest in expected.items():
    assert hashlib.sha256(package.joinpath(name).read_bytes()).hexdigest() == digest, name
print(json.dumps({'version': memstara.__version__, 'verified_files': len(expected)}))
"""
        output = subprocess.check_output(
            [str(python), "-I", "-c", code, str(manifest)], cwd=root, text=True)
        result = json.loads(output)
    print("Isolated wheel installation and packaged bytes verified:", result)
    print("Dependencies intentionally not installed; this is not full runtime acceptance.")


if __name__ == "__main__":
    main()
