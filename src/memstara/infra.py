"""Inspect, or start only existing, explicitly pinned local backing services.

No provisioning, container replacement, migration, volume mutation or .env output.
This is a compatibility path for the legacy host, not a new-host installer.
"""

import argparse
import json
import subprocess


EXPECTED_VOLUMES = {
    "motoro-postgres": "agentic_core_postgres_data",
    "memstara-postgres": "memstara_postgres_data",
    "motoro-redis": None,
}
DATA_PATH = "/var/lib/postgresql/data"


def docker(*args):
    result = subprocess.run(
        ["docker", *args],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode:
        # Do not echo arbitrary Docker diagnostics or configuration values.
        raise RuntimeError(
            f"Docker {args[0]} failed (exit {result.returncode}); check Docker access and service availability"
        )
    return result.stdout.strip()


def validate_mount(name, mounts):
    expected = EXPECTED_VOLUMES[name]
    if expected is None:
        return
    data = [m for m in mounts if m.get("Destination") == DATA_PATH]
    if len(data) != 1 or data[0].get("Type") != "volume" or data[0].get("Name") != expected:
        raise RuntimeError(f"Refusing {name}: PostgreSQL data volume must be {expected}; no services changed")


def inspect_all():
    records = {}
    for name in EXPECTED_VOLUMES:
        # Request only state and mounts, never inspect's Config.Env.
        raw = docker("inspect", "--format", '{"state":{{json .State.Status}},"mounts":{{json .Mounts}}}', name)
        record = json.loads(raw)
        validate_mount(name, record["mounts"])
        if record["state"] not in {"running", "exited", "created"}:
            raise RuntimeError(f"Refusing {name}: unexpected state {record['state']}; investigate before starting")
        records[name] = record
    return records


def check(start=False):
    # Validate ALL containers before starting any; missing containers fail closed.
    records = inspect_all()
    if start:
        for name, record in records.items():
            if record["state"] != "running":
                docker("start", name)
        records = inspect_all()
    for name, record in records.items():
        print(f"{name}: {record['state']}; volume={EXPECTED_VOLUMES[name] or 'not applicable'}")
    if any(r["state"] != "running" for r in records.values()):
        raise RuntimeError("A service is stopped; use --start-existing only when startup is intended")
    for container, user, database in (
        ("motoro-postgres", "agentic", "motoro"),
        ("memstara-postgres", "memstara", "memstara"),
    ):
        docker("exec", container, "pg_isready", "-U", user, "-d", database)
    if docker("exec", "motoro-redis", "redis-cli", "ping") != "PONG":
        raise RuntimeError("Redis did not return PONG")
    print("PostgreSQL readiness and Redis PONG verified. No schema or volume changes performed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start-existing",
        action="store_true",
        help="Start stopped named containers after checking all pinned volumes; never create or replace",
    )
    args = parser.parse_args()
    try:
        check(args.start_existing)
    except (RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"Infrastructure check failed: {exc}\n")


if __name__ == "__main__":
    main()
