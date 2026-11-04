"""Back up the stopped application's databases and files before history reset.

Run from the repository root. A COMPLETE.json manifest is written only after
archive reads and PostgreSQL archive listing succeed. Partial backups are kept
for diagnosis, never treated as successful backups.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone


def run(args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


ARCHIVE_SCRIPT = """import json, sys, tarfile
with tarfile.open(fileobj=sys.stdout.buffer, mode='w|gz', dereference=False) as archive:
    for name, source in json.loads(sys.argv[1]).items():
        archive.add(source, arcname=name)
"""


def archive_files(sources, destination):
    # Container-owned private settings are intentionally unreadable on the host.
    # Mount only the backup sources read-only and bypass the service entrypoint.
    # Stream to a host-owned file; never chmod/chown the original private files.
    command = ['docker', 'compose', 'run', '--rm', '--no-deps', '-T',
               '--user', '0:0', '--entrypoint', 'python']
    mounted = {}
    for index, (name, source) in enumerate(sources.items()):
        target = f'/backup-source/{index}'
        command.extend(['-v', f'{source}:{target}:ro'])
        mounted[name] = target
    command.extend(['control', '-c', ARCHIVE_SCRIPT, json.dumps(mounted)])
    with destination.open('wb') as stream:
        run(command, stdout=stream)


def backup(destination):
    os.umask(0o077)
    project = Path.cwd()
    config = json.loads(subprocess.check_output(["docker", "compose", "config", "--format", "json"]))
    mounts = {v["target"]: Path(v["source"]).resolve()
              for v in config["services"]["control"]["volumes"] if v["type"] == "bind"}
    sources = {"outputs": mounts["/app/outputs"], "user-inputs": mounts["/app/user-inputs"]}
    for name in (".env", ".memstara", "compose.override.yaml"):
        if (project / name).exists():
            sources[name] = project / name
    parent = Path(destination).resolve()
    for source in sources.values():
        if parent == source or source in parent.parents:
            raise RuntimeError("Backup destination must be outside the archived source directories")
        if not source.exists():
            raise RuntimeError("Required backup source is missing")
    parent.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime("reset-%Y%m%dT%H%M%SZ-"), dir=parent))
    print(f"Backing up execution history to: {folder}", flush=True)
    for service in ("board", "runtime"):
        archive = folder / (service + ".dump")
        with archive.open("wb") as stream:
            run(["docker", "compose", "exec", "-T", service, "sh", "-ec",
                 '. /settings/postgres.env; exec pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom'], stdout=stream)
        if not archive.stat().st_size:
            raise RuntimeError("Database backup is empty")
        with archive.open("rb") as stream:
            run(["docker", "compose", "exec", "-T", service, "pg_restore", "--list"],
                stdin=stream, stdout=subprocess.DEVNULL)
    files = folder / "files.tar.gz"
    archive_files(sources, files)
    # Read every archived payload, rather than just checking the archive header.
    with tarfile.open(files, "r:gz") as archive:
        for member in archive:
            if member.isfile():
                with archive.extractfile(member) as stream:
                    while stream.read(1024 * 1024):
                        pass
    checksums = {}
    for path in sorted(folder.iterdir()):
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        checksums[path.name] = {"sha256": digest.hexdigest(), "bytes": path.stat().st_size}
    manifest = {"created_at": datetime.now(timezone.utc).isoformat(), "project": str(project),
                "sources": {k: str(v) for k, v in sources.items()}, "files": checksums,
                "database_format": "PostgreSQL custom archives; schema and all data, not cluster roles",
                "validation": "pg_restore --list and full file archive read; restore not rehearsed"}
    (folder / "COMPLETE.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Backup verified: {folder}. Keep this private: it includes settings and credentials.", flush=True)
    return folder


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", required=True)
    args = parser.parse_args()
    backup(args.destination)
