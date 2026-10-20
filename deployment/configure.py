"""Validate the mounted .env and write restricted per-service startup settings."""

import json
import os
from pathlib import Path
import shlex
import sys

from memstara.container_config import ConfigurationError, derive, provision_viewers
from memstara.operational import resolve


def main():
    try:
        values, _ = resolve({}, file=Path("/app/.env"))
        # Compose uses shell interpolation for host bindings. Refuse a shell value
        # that disagrees with the mounted file instead of silently mixing sources.
        for name in (
            "MEMSTARA_WEB_PORT",
            "MEMSTARA_OUTPUT_DIR",
            "HF_HOME",
            "MEMSTARA_INPUTS_DIR",
            "COMPOSE_PROJECT_NAME",
        ):
            supplied = os.environ.get("COMPOSE_" + name)
            expected = values.get(name, "memstara-app" if name == "COMPOSE_PROJECT_NAME" else "")
            if name in ("MEMSTARA_OUTPUT_DIR", "HF_HOME", "MEMSTARA_INPUTS_DIR") and supplied:
                supplied = str((Path("/app") / supplied).resolve())
            if supplied is not None and supplied != expected:
                raise ConfigurationError(f"{name}: shell/Compose setting differs from .env; unset the shell override")
        saved = Path("/generated/control/settings.json")
        previous = json.loads(saved.read_text()) if saved.exists() else {}
        values = provision_viewers(values, previous)
        groups = derive(values, root=Path("/app"))
        for service, settings in groups.items():
            root = Path("/generated") / service
            root.mkdir(parents=True, exist_ok=True)
            root.chmod(0o700)
            path = root / "settings.json"
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w") as stream:
                json.dump(settings, stream)
            if service in ("board", "runtime"):
                path = root / "postgres.env"
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w") as stream:
                    stream.write("\n".join(f"export {k}={shlex.quote(v)}" for k, v in settings.items()) + "\n")
        print("Configuration validated; isolated service settings generated. No model call performed.")
        return 0
    except ConfigurationError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (ValueError, OSError):
        # Detailed errors from URL/IO parsing may contain credentials.
        print(
            "Configuration rejected. Check .env values, mounted input paths and shell overrides. No values logged.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
