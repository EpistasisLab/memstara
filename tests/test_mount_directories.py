import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    'mount_directories', Path(__file__).resolve().parents[1] / 'deployment/mount_directories.py'
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_only_directory_binds_are_created_and_deduplicated():
    volumes = [
        {'type': 'bind', 'source': '/a path/inputs', 'target': '/app/user-inputs'},
        {'type': 'bind', 'source': '/a path/inputs', 'target': '/app/user-inputs'},
        {'type': 'bind', 'source': '/a/.env', 'target': '/app/.env'},
        {'type': 'volume', 'source': 'db', 'target': '/var/lib/postgresql/data'},
    ]
    assert module.directories({'services': {'configure': {'volumes': volumes}}}) == ['/a path/inputs']


@pytest.mark.parametrize('source', ['relative', '/a\nb', '/a\rb', '/a\x00b'])
def test_rejects_ambiguous_paths(source):
    with pytest.raises(ValueError):
        module.directories({'services': {'control': {'volumes': [
            {'type': 'bind', 'source': source, 'target': '/app/outputs'}
        ]}}})
