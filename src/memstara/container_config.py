"""Derive isolated container settings from the same project configuration as CLI.

No shell evaluation, provider requests or database mutations occur here. Owner
credentials stay in bootstrap/control; the viewer receives read-only DSNs only.
"""

from __future__ import annotations

from pathlib import Path
import secrets
from urllib.parse import unquote, urlsplit, urlunsplit

from memstara.operational import PATH_KEYS, check


class ConfigurationError(ValueError):
    """A diagnostic containing setting names and instructions, never values."""


def database(url: str, key: str, host: str) -> tuple[str, dict[str, str]]:
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme not in ("postgresql", "postgresql+asyncpg")
            or parsed.hostname not in ("localhost", "127.0.0.1", host)
            or not parsed.username
            or not parsed.password
            or not parsed.path.strip("/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError()
        user, password, name = unquote(parsed.username), unquote(parsed.password), unquote(parsed.path[1:])
        if any(c in user + password + name for c in ("\x00", "\n", "\r")):
            raise ValueError()
        authority = parsed.netloc.rsplit("@", 1)[0]
        mapped = urlunsplit((parsed.scheme, authority + "@" + host + ":5432", parsed.path, "", ""))
        return mapped, {"POSTGRES_USER": user, "POSTGRES_PASSWORD": password, "POSTGRES_DB": name}
    except ValueError:
        raise ConfigurationError(
            f"{key}: use an explicit local PostgreSQL user, password and database; percent-encode URL credentials"
        ) from None


def provision_viewers(values: dict[str, str], previous: dict[str, str]) -> dict[str, str]:
    """Derive private reader credentials once; reuse persisted credentials on restart."""
    result = dict(values)
    for owner_key, host, reader_key in (
        ("MEMSTARA_DATABASE_URL", "board", "MEMSTARA_VIEWER_DSN"),
        ("MOTORO_DATABASE_URL", "runtime", "CORE_VIEWER_DSN"),
    ):
        if result.get(reader_key, "").strip():
            continue
        mapped, owner = database(result.get(owner_key, ""), owner_key, host)
        if previous.get(reader_key):
            if previous.get(owner_key) != mapped:
                raise ConfigurationError(f"{owner_key}: changed owner settings require explicit viewer credentials")
            result[reader_key] = previous[reader_key]
            continue
        role = "memstara_viewer"
        if owner["POSTGRES_USER"] == role:
            role = "memstara_readonly"
        parsed = urlsplit(mapped)
        result[reader_key] = urlunsplit(("postgresql", role + ":" + secrets.token_urlsafe(32)
                                        + "@" + host + ":5432", parsed.path, "", ""))
    return result


def derive(values: dict[str, str], *, root: Path) -> dict[str, dict[str, str]]:
    """Reject unsupported input paths and split settings by least-privilege consumer."""
    control = dict(values)
    groups: dict[str, dict[str, str]] = {}
    for key, host, viewer_key in (
        ("MEMSTARA_DATABASE_URL", "board", "MEMSTARA_VIEWER_DSN"),
        ("MOTORO_DATABASE_URL", "runtime", "CORE_VIEWER_DSN"),
    ):
        mapped, owner = database(values.get(key, ""), key, host)
        view_url, viewer = database(values.get(viewer_key, ""), viewer_key, host)
        if owner["POSTGRES_DB"] != viewer["POSTGRES_DB"]:
            raise ConfigurationError(f"{viewer_key}: database must match {key}")
        if owner["POSTGRES_USER"] == viewer["POSTGRES_USER"]:
            raise ConfigurationError(f"{viewer_key}: use a separate read-only role")
        groups[host] = owner
        control[key] = mapped
        control[viewer_key] = view_url.replace("postgresql+asyncpg://", "postgresql://", 1)
    redis = urlsplit(values.get("MOTORO_REDIS_URL", ""))
    if (
        redis.scheme != "redis"
        or redis.hostname not in ("localhost", "127.0.0.1", "redis")
        or redis.username
        or redis.password
        or redis.query
        or redis.fragment
        or not redis.path.strip("/").isdigit()
    ):
        raise ValueError("MOTORO_REDIS_URL: Docker supports local redis://host:port/database without credentials")
    control["MOTORO_REDIS_URL"] = f"redis://redis:6379{redis.path}"
    # Bind mount destinations are stable even when their host paths change.
    control["MEMSTARA_OUTPUT_DIR"] = str(root / "outputs")
    control["HF_HOME"] = str(root / "cache")
    control["MEMSTARA_INPUTS_DIR"] = str(root / "user-inputs")
    allowed = [root / name for name in ("examples", "user-inputs", "outputs", "cache", "src/memstara/resources")]
    path_errors = []
    for key in sorted(PATH_KEYS - {"MEMSTARA_OUTPUT_DIR", "HF_HOME", "MEMSTARA_INPUTS_DIR"}):
        if control.get(key):
            path = Path(control[key]).resolve()
            for source_key, destination in (
                ("MEMSTARA_INPUTS_DIR", "user-inputs"),
                ("MEMSTARA_OUTPUT_DIR", "outputs"),
                ("HF_HOME", "cache"),
            ):
                source = Path(values.get(source_key) or root / destination).resolve()
                if path == source or source in path.parents:
                    path = root / destination / path.relative_to(source)
                    control[key] = str(path)
                    break
            if not any(path == base or base in path.parents for base in allowed):
                path_errors.append(
                    f"{key}: path is outside Docker mounts. Use examples/, user-inputs/, outputs/, "
                    "cache/ or bundled resources; unset unused defaults."
                )
            elif not path.exists() and key not in {"HF_HUB_CACHE", "MEMSTARA_USER_SKILLS_DIR"}:
                path_errors.append(
                    f"{key}: file or directory is missing. Supply the input under user-inputs/ "
                    "and correct .env, or unset this default to choose inputs in the app."
                )
    if path_errors:
        raise ConfigurationError("Fix these .env paths before starting:\n- " + "\n- ".join(path_errors))
    control["MEMSTARA_CONFIG_MODE"] = "environment"
    control["MEMSTARA_CONFIG_ORIGIN_FILE"] = "/app/.env"
    control["MEMSTARA_CONTAINER_MODE"] = "1"
    control["MEMSTARA_CONTROL_PORT"] = "8072"
    control["MEMSTARA_API_PORT"] = "8000"
    # Public port is retained for origin checks; it is not the container listener.
    # The GUI can supply an experiment's model after the application starts.
    # Execution still uses operational.check's strict default with resolved credentials.
    result = check(control, require_models=False)
    if not result["configuration_valid"]:
        raise ConfigurationError("; ".join(result["errors"]))
    groups["control"] = control
    groups["api"] = {key: control[key] for key in ("MEMSTARA_VIEWER_DSN", "CORE_VIEWER_DSN")}
    groups["api"].update(MEMSTARA_RUNS_DIR="/runs", HF_HOME="/root/.cache/huggingface", VIEWER_CORS="")
    return groups
