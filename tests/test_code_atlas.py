"""Source-map extraction must resolve local code without indexing private data."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("code_atlas", Path(__file__).parents[1] / "scripts/build_code_atlas.py")
atlas = importlib.util.module_from_spec(spec)
spec.loader.exec_module(atlas)


def test_excludes_secrets_artifacts_and_personal_notes():
    for path in [
        ".env",
        "outputs/run/code.py",
        "docs/private.md",
        "daily_log/log.py",
        "src/memstara/CLAUDE.md",
        "viewer/web/src/developer/inventory.json",
        "src/memstara/notes.md",
    ]:
        assert not atlas.eligible(path), path
    assert atlas.eligible("src/memstara/prompts/board/hypothesis.md")
    assert atlas.eligible("viewer/web/src/App.tsx")


def test_python_relative_absolute_and_flat_api_imports():
    paths = {
        "src/memstara/pipeline/board.py",
        "src/memstara/pipeline/runtime.py",
        "src/memstara/config.py",
        "viewer/api/scene.py",
        "viewer/api/main.py",
    }
    symbols, refs, routes = atlas.analyze(
        "src/memstara/pipeline/board.py",
        "from . import runtime\nfrom memstara.config import Settings\nasync def start():\n    pass\n",
        paths,
    )
    assert {r["target"] for r in refs} == {"src/memstara/pipeline/runtime.py", "src/memstara/config.py"}
    assert symbols == [{"name": "start", "line": 3, "kind": "function"}]
    _, refs, routes = atlas.analyze(
        "viewer/api/main.py", 'import scene\n@app.get("/api/snapshot")\ndef snapshot():\n    pass\n', paths
    )
    assert refs[0]["target"] == "viewer/api/scene.py"
    assert {"name": "GET /api/snapshot", "line": 2, "kind": "route"} in routes


def test_typescript_imports_and_line_numbers():
    paths = {"viewer/web/src/App.tsx", "viewer/web/src/store/viewer.ts", "viewer/web/src/panels/index.tsx"}
    source = 'import {useViewer} from "./store/viewer";\nconst panel = import("./panels");\nexport function App() {}\n'
    symbols, refs, _ = atlas.analyze("viewer/web/src/App.tsx", source, paths)
    assert {r["target"] for r in refs} == paths - {"viewer/web/src/App.tsx"}
    assert {"name": "App", "line": 3, "kind": "function"} in symbols


def test_curated_entrypoints_and_reading_paths_exist():
    import re

    text = (atlas.ROOT / "viewer/web/src/developer/architecture.ts").read_text()
    paths = re.findall(r"'(?:src/memstara|viewer/|scripts/)[^']+'", text)
    assert paths
    for path in paths:
        assert (atlas.ROOT / path.strip("'")).is_file(), path
