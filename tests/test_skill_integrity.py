"""Protect original and archived bytes without rewriting or trusting a new hash."""

import json

import pytest

from memstara import skill_integrity as integrity


@pytest.fixture
def baseline(tmp_path):
    root = tmp_path / "contributed"
    (root / "old").mkdir(parents=True)
    (root / "current.md").write_bytes(b"# Original\r\nExact bytes\r\n")
    (root / "old" / "previous.md").write_text("# Historical instructions")
    roots = integrity.roots_from_options([f"skills={root}"])
    manifest = tmp_path / "baseline.json"
    digest = integrity.snapshot(roots, manifest)
    return roots, manifest, digest


def test_snapshot_and_verification_preserve_sources_and_hide_absolute_paths(baseline):
    roots, manifest, digest = baseline
    before = {str(p): p.read_bytes() for p in roots["skills"].rglob("*") if p.is_file()}
    result = integrity.verify(roots, manifest, digest)
    assert result["status"] == "unchanged_since_snapshot"
    assert result["checked_files"] == 2
    assert result["original_authenticity"] == "not_established_by_this_check"
    assert str(roots["skills"]) not in manifest.read_text()
    assert "Exact bytes" not in manifest.read_text()
    assert before == {str(p): p.read_bytes() for p in roots["skills"].rglob("*") if p.is_file()}


@pytest.mark.parametrize("operation", ["edit", "delete", "add", "archive", "rename"])
def test_detects_changes_without_rebaselining(baseline, operation):
    roots, manifest, digest = baseline
    root = roots["skills"]
    before = manifest.read_bytes()
    if operation == "edit":
        (root / "current.md").write_text("# Changed")
    elif operation == "delete":
        (root / "current.md").unlink()
    elif operation == "add":
        (root / "new.md").write_text("# Newly supplied")
    elif operation == "archive":
        (root / "old" / "previous.md").write_text("# Changed archive")
    else:
        (root / "current.md").rename(root / "renamed.md")
    result = integrity.verify(roots, manifest, digest)
    assert result["status"] == "changed"
    assert result["changed"] or result["added"] or result["missing"]
    assert manifest.read_bytes() == before


def test_overwrite_and_replaced_manifest_are_rejected(baseline):
    roots, manifest, digest = baseline
    with pytest.raises(FileExistsError):
        integrity.snapshot(roots, manifest)
    data = json.loads(manifest.read_text())
    data["files"]["skills/current.md"]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="digest mismatch"):
        integrity.verify(roots, manifest, digest)


@pytest.mark.parametrize("directory", [False, True])
def test_symlinks_cannot_replace_protected_entries(baseline, tmp_path, directory):
    roots, manifest, digest = baseline
    destination = tmp_path / "outside"
    destination.mkdir()
    (destination / "secret.md").write_text("Must not be included")
    (roots["skills"] / "link").symlink_to(destination if directory else destination / "secret.md")
    with pytest.raises(ValueError, match="symlinks"):
        integrity.verify(roots, manifest, digest)


def test_refuses_scope_changes_and_in_tree_manifest(baseline):
    roots, manifest, digest = baseline
    with pytest.raises(ValueError, match="aliases differ"):
        integrity.verify({"renamed": roots["skills"]}, manifest, digest)
    with pytest.raises(ValueError, match="outside"):
        integrity.snapshot(roots, roots["skills"] / "manifest.json")
    with pytest.raises(ValueError, match="overlap"):
        integrity.roots_from_options([f"a={roots['skills']}", f"b={roots['skills'] / 'old'}"])


def test_missing_root_and_empty_baseline_are_errors(tmp_path):
    with pytest.raises(ValueError, match="directory"):
        integrity.roots_from_options([f"skills={tmp_path / 'missing'}"])
    roots = integrity.roots_from_options([f"skills={tmp_path}"])
    with pytest.raises(ValueError, match="empty"):
        integrity.inventory(roots)


def test_cli_exit_codes_and_required_pin(baseline, capsys):
    roots, manifest, digest = baseline
    args = ["verify", "--root", f"skills={roots['skills']}", "--manifest", str(manifest)]
    assert integrity.main(args) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"
    assert integrity.main([*args, "--manifest-sha256", digest]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "unchanged_since_snapshot"
    (roots["skills"] / "current.md").unlink()
    assert integrity.main([*args, "--manifest-sha256", digest]) == 1
    assert json.loads(capsys.readouterr().out)["missing"] == ["skills/current.md"]


def test_directory_read_error_cannot_silently_shrink_inventory(baseline, monkeypatch):
    roots, manifest, digest = baseline

    def denied(*args, onerror, **kwargs):
        onerror(PermissionError("synthetic unreadable directory"))
        return iter(())

    monkeypatch.setattr(integrity.os, "walk", denied)
    with pytest.raises(PermissionError):
        integrity.verify(roots, manifest, digest)
