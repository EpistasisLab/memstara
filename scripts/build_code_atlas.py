"""Build a metadata-only code atlas; never read credentials, datasets or run artifacts.

Run from the repository: .venv/bin/python scripts/build_code_atlas.py [--check]
Python dependencies use AST imports. JS/TS imports use a conservative lexical scan;
dynamic expressions, aliases and runtime tool dispatch are not a call graph.
"""

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "viewer/web/src/developer/inventory.json"
PREFIXES = ("src/memstara/", "viewer/api/", "viewer/web/src/", "tests/", "viewer/web/tests/", "scripts/")
EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".mjs", ".css", ".md"}


def eligible(path):
    p = Path(path)
    return (
        path.startswith(PREFIXES)
        and p.suffix in EXTENSIONS
        and p.name not in {"CLAUDE.md", "AGENTS.md"}
        and "_KR" not in p.name
        and (p.suffix != ".md" or "/prompts/" in path or "/playbooks/" in path)
    )


def layer(path):
    if path.startswith(("tests/", "viewer/web/tests/")):
        return "tests"
    if path.startswith("scripts/"):
        return "scripts"
    if path.startswith("viewer/web/"):
        return "frontend"
    if path.startswith("viewer/api/"):
        return "api"
    for folder, name in [
        ("control", "control"),
        ("pipeline", "pipeline"),
        ("mcp_servers", "tools"),
        ("matcher", "matcher"),
        ("prompts", "instructions"),
        ("playbooks", "instructions"),
    ]:
        if path.startswith(f"src/memstara/{folder}/"):
            return name
    return "foundation"


def resolve_file(base, paths):
    base = str(Path(base)).replace("\\", "/")
    # Resolve .. without following any filesystem symlinks.
    parts = []
    for part in base.split("/"):
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    base = "/".join(parts)
    return next(
        (
            p
            for p in [
                base,
                base + ".py",
                base + "/__init__.py",
                base + ".ts",
                base + ".tsx",
                base + ".js",
                base + ".mjs",
                base + ".css",
                base + "/index.ts",
                base + "/index.tsx",
            ]
            if p in paths
        ),
        None,
    )


def analyze(path, text, paths):
    symbols, refs, routes = [], [], []
    if path.endswith(".py"):
        tree = ast.parse(text, filename=path)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                symbols.append(
                    {
                        "name": node.name,
                        "line": node.lineno,
                        "kind": "class" if isinstance(node, ast.ClassDef) else "function",
                    }
                )
                for d in node.decorator_list:
                    if (
                        isinstance(d, ast.Call)
                        and isinstance(d.func, ast.Attribute)
                        and d.func.attr in {"get", "post", "put", "delete", "patch"}
                        and d.args
                        and isinstance(d.args[0], ast.Constant)
                        and isinstance(d.args[0].value, str)
                    ):
                        routes.append(
                            {"name": d.func.attr.upper() + " " + d.args[0].value, "line": d.lineno, "kind": "route"}
                        )
            if isinstance(node, ast.Import):
                refs.extend((a.name, 0, node.lineno) for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                refs.append((node.module or "", node.level, node.lineno))
                refs.extend(
                    (".".join(filter(None, [node.module, a.name])), node.level, node.lineno)
                    for a in node.names
                    if a.name != "*"
                )
        imports = []
        for name, level, line in refs:
            candidates = []
            if level:
                parent = Path(path).parent
                for _ in range(level - 1):
                    parent = parent.parent
                candidates.append(str(parent / name.replace(".", "/")))
            else:
                candidates.extend(["src/" + name.replace(".", "/"), "viewer/api/" + name.replace(".", "/")])
            target = next((p for c in candidates if (p := resolve_file(c, paths))), None)
            if target and target != path:
                imports.append({"target": target, "line": line})
    else:
        imports = []
        pattern = r"""(?:\bfrom\s*|\bimport\s*\(\s*|\bimport\s*)['"]([^'"\n]+)['"]"""
        for m in re.finditer(pattern, text):
            if m[1].startswith("."):
                target = resolve_file(str(Path(path).parent / m[1]), paths)
                if target and target != path:
                    imports.append({"target": target, "line": text.count("\n", 0, m.start()) + 1})
        if Path(path).suffix in {".ts", ".tsx", ".js", ".mjs"}:
            pattern = r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?(function|class|interface|type|const)\s+(\w+)"
            for m in re.finditer(pattern, text, re.M):
                symbols.append({"name": m[2], "line": text.count("\n", 0, m.start()) + 1, "kind": m[1]})
    # Literal endpoint references, including the control service's manual router.
    for m in re.finditer(r"""['"](/(?:api|control)/[^'"\n]*)['"]""", text):
        name = m[1]
        if len(name) <= 180:
            routes.append({"name": name, "line": text.count("\n", 0, m.start()) + 1, "kind": "path reference"})

    def unique(rows):
        return sorted({json.dumps(r, sort_keys=True): r for r in rows}.values(), key=lambda r: r["line"])

    return unique(symbols), unique(imports), unique(routes)


def build(root=ROOT):
    names = (
        subprocess.check_output(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=root)
        .decode()
        .split("\0")
    )
    paths = sorted({p for p in names if eligible(p) and (root / p).is_file() and not (root / p).is_symlink()})
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root).decode().strip()
    modified = set(subprocess.check_output(["git", "diff", "HEAD", "--name-only"], cwd=root).decode().splitlines())
    tracked = set(subprocess.check_output(["git", "ls-files"], cwd=root).decode().splitlines())
    files = []
    for path in paths:
        content = (root / path).read_text(encoding="utf-8")
        symbols, imports, routes = analyze(path, content, set(paths))
        files.append(
            {
                "path": path,
                "layer": layer(path),
                "lines": len(content.splitlines()),
                "hash": hashlib.sha256(content.encode()).hexdigest()[:12],
                "localChanges": path in modified or path not in tracked,
                "symbols": symbols,
                "imports": imports,
                "routes": routes,
            }
        )
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()[:16]
    return {"version": 1, "revision": head, "fingerprint": digest, "files": files}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the inventory is stale")
    args = parser.parse_args()
    if sys.version_info < (3, 12):  # noqa: UP036 -- system Python may predate the project environment.
        raise SystemExit("Use Python 3.12+: .venv/bin/python scripts/build_code_atlas.py")
    output = json.dumps(build(), ensure_ascii=True, separators=(",", ":")) + "\n"
    if args.check:
        if not DEST.exists() or DEST.read_text() != output:
            raise SystemExit("Code atlas is stale. Run .venv/bin/python scripts/build_code_atlas.py")
        print("Code atlas matches the working tree.")
    else:
        DEST.parent.mkdir(parents=True, exist_ok=True)
        DEST.write_text(output)
        print(f"Indexed {len(json.loads(output)['files'])} files into {DEST.relative_to(ROOT)}")
