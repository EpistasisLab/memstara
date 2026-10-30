"""Verify saved fit evidence before reusing it; never refit to hide missing artifacts."""

import hashlib
import json
from pathlib import Path


def verify_result(result, output_root):
    """Validate bundle receipts and every recorded file without unpickling models."""
    if result.get("status") == "failed" or result.get("error"):
        raise ValueError("The saved ML attempt failed; inspect its evidence before retry")
    root = Path(output_root).resolve()
    receipts = []

    def collect(value):
        if isinstance(value, dict):
            receipt = value.get("reproducibility")
            if isinstance(receipt, dict):
                receipts.append(receipt)
            for key, child in value.items():
                if key != "reproducibility":
                    collect(child)
        elif isinstance(value, list):
            for child in value:
                collect(child)

    collect(result)
    if not receipts:
        raise ValueError("Saved ML result has no verifiable model bundle; automatic reuse is unavailable")
    verified = set()
    for receipt in receipts:
        try:
            bundle = Path(receipt["bundle_path"]).resolve()
            bundle.relative_to(root)
            manifest_path = bundle / "manifest.json"
            raw = manifest_path.read_bytes()
            expected = receipt["manifest_sha256"]
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError("Manifest checksum mismatch")
            if (str(bundle), expected) in verified:
                continue
            manifest = json.loads(raw)
            files = manifest["files"]
            if not files or not any(name.startswith("model-") and name.endswith(".joblib") for name in files):
                raise ValueError("Model artifact missing from manifest")
            for name, checksum in files.items():
                if Path(name).name != name:
                    raise ValueError("Invalid artifact filename")
                path = (bundle / name).resolve()
                path.relative_to(bundle)
                if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
                    raise ValueError("Artifact checksum mismatch")
            verified.add((str(bundle), expected))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise ValueError("Saved ML artifacts are missing or changed; refusing reuse and automatic refit") from exc
