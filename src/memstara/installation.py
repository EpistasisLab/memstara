"""Generated local Docker identity and credentials; never a user settings file."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets

from dotenv import dotenv_values

KEYS = (
    "MEMSTARA_DATABASE_URL",
    "MOTORO_DATABASE_URL",
    "MOTORO_REDIS_URL",
    "MEMSTARA_VIEWER_DSN",
    "CORE_VIEWER_DSN",
    "COMPOSE_PROJECT_NAME",
    "MEMSTARA_BOARD_VOLUME_NAME",
    "MEMSTARA_RUNTIME_VOLUME_NAME",
)
MARKER = "memstara_generated_installation"


def read(root: Path) -> dict:
    path = root / ".memstara" / "installation.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("settings"), dict):
        raise ValueError("Invalid generated installation state; restore its backup")
    settings = data["settings"]
    required = {"COMPOSE_PROJECT_NAME", "MEMSTARA_DATABASE_URL", "MOTORO_DATABASE_URL", "MOTORO_REDIS_URL"}
    if not required.issubset(settings) or any(
        k not in KEYS or not isinstance(v, str) or not v for k, v in settings.items()
    ):
        raise ValueError("Incomplete generated installation state; restore its backup")
    return settings


def _write(path: Path, text: str):
    temp = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(text)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def prepare(root: Path):
    """Retain explicit legacy identities; otherwise generate once and persist."""
    raw = dotenv_values(root / ".env", interpolate=False)
    override = root / "compose.override.yaml"
    if (root / "compose.override.yml").exists():
        raise ValueError("Existing compose.override.yml requires migration review; nothing replaced")
    if override.exists():
        try:
            previous = json.loads(override.read_text())
        except ValueError:
            raise ValueError("Existing Compose override requires migration review") from None
        if previous.get("x-memstara-generated") != MARKER:
            raise ValueError("Existing Compose override is not generated; nothing replaced")
    settings = read(root)
    if override.exists() and not settings:
        raise ValueError("Missing installation state; restore its backup before starting")
    for key in KEYS:
        if raw.get(key):
            if key in settings and raw[key] != settings[key]:
                raise ValueError(f"{key} conflicts with saved installation; explicit migration required")
            settings[key] = raw[key]
    if not settings.get("COMPOSE_PROJECT_NAME"):
        name = re.sub(r"[^a-z0-9_-]", "-", root.name.lower()).strip("-_") or "memstara"
        settings["COMPOSE_PROJECT_NAME"] = name[:35] + "-" + secrets.token_hex(4)
    for key, scheme, user, port in [
        ("MEMSTARA_DATABASE_URL", "postgresql", "memstara", 55641),
        ("MOTORO_DATABASE_URL", "postgresql+asyncpg", "motoro", 55642),
    ]:
        settings.setdefault(key, f"{scheme}://{user}:{secrets.token_urlsafe(32)}@127.0.0.1:{port}/{user}")
    settings.setdefault("MOTORO_REDIS_URL", "redis://127.0.0.1:56391/0")
    generated = {"x-memstara-generated": MARKER, "name": settings["COMPOSE_PROJECT_NAME"]}
    volumes = {}
    for key, volume in [("MEMSTARA_BOARD_VOLUME_NAME", "board-data"), ("MEMSTARA_RUNTIME_VOLUME_NAME", "runtime-data")]:
        if settings.get(key):
            volumes[volume] = {"external": True, "name": settings[key]}
    if volumes:
        generated["volumes"] = volumes
    directory = root / ".memstara"
    directory.mkdir(mode=0o700, exist_ok=True)
    directory.chmod(0o700)
    _write(directory / "installation.json", json.dumps({"version": 1, "settings": settings}, indent=2) + "\n")
    _write(override, json.dumps(generated, indent=2) + "\n")


if __name__ == "__main__":
    import sys

    try:
        prepare(Path(sys.argv[1]))
        print("Local installation identity prepared. Credentials and existing storage retained; no values logged.")
    except (ValueError, OSError):
        print(
            "Installation preparation failed. Check generated state and existing overrides; no values logged.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
