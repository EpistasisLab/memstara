"""Read-only contributed-file inventory with an externally pinned manifest digest.

A snapshot establishes observed bytes, not contributor authenticity or permission
to redistribute. Keep manifests and their independently retained digests private.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA = 1


def roots_from_options(values: list[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for value in values:
        alias, separator, raw = value.partition("=")
        if not separator or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]*", alias) or not raw or alias in roots:
            raise ValueError("Use unique root aliases in ALIAS=DIRECTORY form")
        path = Path(raw).expanduser()
        if path.is_symlink() or not path.is_dir():
            raise ValueError(f"{alias}: an existing ordinary directory is required")
        root = path.resolve()
        if any(root.is_relative_to(other) or other.is_relative_to(root) for other in roots.values()):
            raise ValueError("Protected roots must not overlap")
        roots[alias] = root
    if not roots:
        raise ValueError("At least one protected root is required")
    return roots


def file_record(path: Path) -> dict[str, Any]:
    # Refuse final-component symlinks even if replaced after directory discovery.
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Protected entries must be regular files")
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
        after = os.fstat(stream.fileno())
        if (before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError("A protected file changed while being read")
    return {"size": after.st_size, "sha256": digest.hexdigest()}


def inventory(roots: dict[str, Path]) -> dict[str, dict[str, Any]]:
    def unreadable(error: OSError) -> None:
        raise error

    files = {}
    for alias, root in sorted(roots.items()):
        if root.is_symlink() or not root.is_dir():
            raise ValueError(f"{alias}: protected root is unavailable")
        for directory, folders, names in os.walk(root, followlinks=False, onerror=unreadable):
            for name in sorted(folders + names):
                path = Path(directory) / name
                if path.is_symlink():
                    raise ValueError(f"{alias}: symlinks are not allowed in a protected inventory")
                if path.is_dir():
                    continue
                if not path.is_file():
                    raise ValueError(f"{alias}: only regular files and directories are supported")
                files[f"{alias}/{path.relative_to(root).as_posix()}"] = file_record(path)
    return files


def snapshot(roots: dict[str, Path], destination: Path) -> str:
    destination = destination.expanduser().absolute()
    if any(destination.resolve().is_relative_to(root) for root in roots.values()):
        raise ValueError("Store the manifest outside the protected roots")
    files = inventory(roots)
    if not files:
        raise ValueError("An empty inventory cannot establish a baseline")
    value = {
        "schema_version": SCHEMA,
        "basis": "observed_snapshot_not_original_authentication",
        "created_at": datetime.now(UTC).isoformat(),
        "roots": sorted(roots),
        "files": files,
    }
    raw = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode()
    # Exclusive creation prevents silently replacing an established baseline.
    with destination.open("xb") as stream:
        stream.write(raw)
    return hashlib.sha256(raw).hexdigest()


def verify(roots: dict[str, Path], manifest: Path, expected_digest: str) -> dict[str, Any]:
    if not re.fullmatch("[0-9a-f]{64}", expected_digest):
        raise ValueError("Provide the independently retained SHA-256 of the baseline manifest")
    raw = manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_digest:
        raise ValueError("Manifest digest mismatch; do not regenerate the baseline to hide a change")
    baseline = json.loads(raw)
    if not isinstance(baseline, dict) or baseline.get("schema_version") != SCHEMA:
        raise ValueError("Unsupported manifest schema")
    if baseline.get("roots") != sorted(roots):
        raise ValueError("Root aliases differ from the baseline; do not omit protected roots")
    previous = baseline.get("files")
    if not isinstance(previous, dict) or not previous:
        raise ValueError("Invalid baseline inventory")
    current = inventory(roots)
    missing = sorted(previous.keys() - current.keys())
    added = sorted(current.keys() - previous.keys())
    changed = sorted(key for key in previous.keys() & current.keys() if previous[key] != current[key])
    return {
        "status": "changed" if missing or added or changed else "unchanged_since_snapshot",
        "manifest_sha256": expected_digest,
        "checked_files": len(current),
        "missing": missing,
        "added": added,
        "changed": changed,
        "original_authenticity": "not_established_by_this_check",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("snapshot", "verify"))
    parser.add_argument("--root", action="append", required=True, metavar="ALIAS=DIRECTORY")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--manifest-sha256", default="")
    args = parser.parse_args(argv)
    try:
        roots = roots_from_options(args.root)
        if args.action == "snapshot":
            if args.manifest_sha256:
                raise ValueError("A digest is supplied only when verifying an existing baseline")
            result = {
                "status": "snapshot_created",
                "manifest_sha256": snapshot(roots, args.manifest),
                "original_authenticity": "not_established_by_this_check",
            }
        else:
            result = verify(roots, args.manifest, args.manifest_sha256)
    except (OSError, ValueError) as error:
        # Do not disclose filesystem paths or source contents from raw OS errors.
        message = str(error) if isinstance(error, ValueError) else type(error).__name__
        print(json.dumps({"status": "error", "error": message}))
        return 2
    print(json.dumps(result, indent=2))
    return 1 if result["status"] == "changed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
