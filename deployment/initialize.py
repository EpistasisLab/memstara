"""Repeatable schema setup and read-only grants; never reset existing data."""

import asyncio
import os
import subprocess
import sys
from urllib.parse import unquote, urlsplit

import asyncpg


def identifier(value):
    return '"' + value.replace('"', '""') + '"'


async def grants(owner_key, viewer_key):
    owner = os.environ[owner_key].replace("postgresql+asyncpg://", "postgresql://", 1)
    viewer = urlsplit(os.environ[viewer_key])
    role = unquote(viewer.username)
    password = unquote(viewer.password)
    db = unquote(viewer.path[1:])
    conn = await asyncpg.connect(owner, timeout=10)
    try:
        await conn.execute("SET standard_conforming_strings = on")
        exists = await conn.fetchval("SELECT 1 FROM pg_roles WHERE rolname=$1", role)
        if not exists:
            literal = "'" + password.replace("'", "''") + "'"
            await conn.execute(f"CREATE ROLE {identifier(role)} LOGIN PASSWORD {literal}")
        # Never silently rotate existing credentials or downgrade another role.
        await conn.execute(f"GRANT CONNECT ON DATABASE {identifier(db)} TO {identifier(role)}")
        await conn.execute(f"GRANT USAGE ON SCHEMA public TO {identifier(role)}")
        await conn.execute(f"GRANT SELECT ON ALL TABLES IN SCHEMA public TO {identifier(role)}")
        await conn.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO {identifier(role)}")
    finally:
        await conn.close()


async def main():
    for owner in ("MEMSTARA_DATABASE_URL", "MOTORO_DATABASE_URL"):
        connection = await asyncpg.connect(
            os.environ[owner].replace("postgresql+asyncpg://", "postgresql://", 1), timeout=10
        )
        await connection.close()
    subprocess.run(
        [sys.executable, "-m", "motoro.migrations", "upgrade", "--url", os.environ["MOTORO_DATABASE_URL"]],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    subprocess.run(
        [sys.executable, "-m", "memstara.blackboard", "--create"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    await grants("MEMSTARA_DATABASE_URL", "MEMSTARA_VIEWER_DSN")
    await grants("MOTORO_DATABASE_URL", "CORE_VIEWER_DSN")
    from memstara.local_setup import probe_connections

    results = await probe_connections(os.environ)
    if not all(v == "connected" for v in results["services"].values()):
        raise RuntimeError("Service connection or read-only grant verification failed")
    print("Schemas initialized and owner/viewer/Redis connections verified. No model call performed.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        print(
            "Database initialization failed. Check configured credentials and existing-volume ownership; "
            "data was not reset.",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
