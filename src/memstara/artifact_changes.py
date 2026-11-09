"""Process-local hints for incremental indexing; full reconciliation verifies all files.

Hints are never authoritative persistence. They remain pending until the mirror
transaction commits. A new process performs a full backfill before using hints.
"""

from pathlib import Path
from threading import RLock

_lock = RLock()
_roots = {}
_generation = 0


def watch(root):
    root = Path(root).resolve()
    with _lock:
        _roots.setdefault(root, {})


def changed(path):
    global _generation
    path = Path(path).absolute()
    if path.name in {"registry_status.json", "registry_metrics.jsonl"}:
        return
    with _lock:
        for root, pending in _roots.items():
            if path.is_relative_to(root):
                _generation += 1
                pending[path] = _generation


def pending(root):
    with _lock:
        return dict(_roots.get(Path(root).resolve(), {}))


def acknowledge(root, observed):
    with _lock:
        current = _roots.get(Path(root).resolve(), {})
        for path, version in observed.items():
            if current.get(path) == version:
                current.pop(path)
