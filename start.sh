#!/bin/sh
# Memstara deployment entry point (POSIX sh).
#
# Usage:
#   ./start.sh
#       Build and recreate the application while retaining saved settings,
#       execution history, research inputs, and persistent database volumes.
#   ./start.sh --reset-execution-history
#       Build first, stop application services, create and verify a backup,
#       remove execution/results history, and then recreate the application.
#       Research, model, agent, and workspace settings are retained.
#   MEMSTARA_BACKUP_DIR=/absolute/backup/path ./start.sh --reset-execution-history
#       Store the reset backup under a custom parent directory.
#
# Requirements: Docker Engine/Desktop with Compose v2; Python 3 on the host
# is additionally required for reset backups. Run as your normal Docker-enabled
# user. Do not add sudo merely to read container-owned private settings: the
# backup helper reads those files through read-only container mounts.
#
# This command restarts services and can interrupt active experiments. It does
# not start experiments or make paid model requests. Use the normal invocation
# for code/configuration updates; the reset flag explicitly authorizes deletion.
# Database volumes are retained; this script never calls `down -v`.
#
# Stop on unhandled command errors and unset variables. Expected failures are
# handled explicitly below to report which deployment phase needs attention.
set -eu
# Resolve all relative deployment and backup paths from this checkout, even
# when the user invokes the script from another working directory.
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

# Accept only the documented modes. Unknown or extra arguments must not be
# silently ignored, especially when the requested operation could delete data.
reset_execution_history=false
if [ "$#" -eq 1 ] && [ "$1" = "--reset-execution-history" ]; then
    reset_execution_history=true
elif [ "$#" -eq 1 ] && { [ "$1" = "--help" ] || [ "$1" = "-h" ]; }; then
    echo "Usage: ./start.sh [--reset-execution-history]"
    echo "Default: build and start; retain all saved records."
    echo "--reset-execution-history: stop experiments, delete execution/results history, preserve settings and research inputs, then start."
    echo "Reset always backs up both databases and output files first; backup failure prevents deletion."
    echo "Set MEMSTARA_BACKUP_DIR to change the backup parent directory (default: ../memstara-execution-backups)."
    exit 0
elif [ "$#" -ne 0 ]; then
    echo "Usage: ./start.sh [--reset-execution-history]" >&2
    exit 2
fi
# Browser authentication is required for static pages and both proxied APIs.
# Credentials stay in the ignored installation directory, outside image layers.
# Configure once (or rotate) with: python3 deployment/setup-web-auth.py
if [ ! -f .memstara/web-auth/htpasswd ] || [ ! -f .memstara/web-auth/client.json ]; then
    echo "Configure browser login first: python3 deployment/setup-web-auth.py" >&2
    exit 1
fi
if [ "$reset_execution_history" = true ]; then
    # Reset is for an existing installation, not first-time provisioning.
    # Validate these prerequisites before creating defaults or stopping services.
    command -v python3 >/dev/null 2>&1 || { echo "Reset backups require Python 3 on the host." >&2; exit 1; }
    if [ ! -f .env ] || [ ! -f deployment/reset-execution-history.py ]; then
        echo "Reset requires the existing .env and cleanup script; nothing was deleted." >&2
        exit 1
    fi
fi
if [ ! -f .env ]; then
    # First-time setup only: never overwrite an existing environment file.
    # Restrict permissions on the newly copied file because it can hold secrets.
    (umask 077; cp .env.example .env)
    echo "Created .env with installation defaults. You can configure the model in Add experiment after startup."
fi
# Check the client, Compose plugin, and daemon separately so each failure has
# an actionable message. No application containers have been restarted yet.
if ! command -v docker >/dev/null 2>&1; then
    echo "Install Docker Desktop (or Docker Engine with Compose v2), then run ./start.sh again." >&2
    exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
    echo "Docker Compose v2 is required. Update Docker, then run ./start.sh again." >&2
    exit 1
fi
if ! docker info >/dev/null 2>&1; then
    echo "Docker is not running. Start Docker Desktop or the Docker daemon, then retry." >&2
    exit 1
fi

# Bootstrap without Compose: installation identity and generated settings may
# not exist yet. The helper writes its image identifier to a temporary file.
# Run installation preparation as the host UID/GID to avoid root-owned setup
# files in the checkout. Temporary-file traps do not remove persistent backups.
bootstrap_image=$(mktemp)
trap 'rm -f "$bootstrap_image"' EXIT HUP INT TERM
if ! sh deployment/build-service.sh --bootstrap "$bootstrap_image"; then
    echo "Could not build the installation preparer. Existing services were not changed." >&2
    exit 1
fi
if ! docker run --rm --user "$(id -u):$(id -g)" --mount "type=bind,source=$(pwd),target=/project" "$(cat "$bootstrap_image")" python -m memstara.installation /project; then
    echo "Could not prepare local installation settings. Do not delete existing data volumes." >&2
    exit 1
fi
# Installation settings come from .env, including an automatically selected port.
# Clear an inherited shell override so Compose uses the installation's port.
# Keep the preparer image identifier for a possible later port-conflict retry.
unset MEMSTARA_WEB_PORT
preparer_image=$(cat "$bootstrap_image")
if ! sh deployment/select-web-port.sh "$preparer_image"; then
    echo "Could not select a web port. Existing application services were not restarted." >&2
    exit 1
fi
rm -f "$bootstrap_image"

# Create bind directories on the host, not through Docker Desktop's file-sharing VM.
# Resolve paths through Compose so .env interpolation and overrides stay authoritative.
# Keep the resolved configuration in a temporary file instead of printing it;
# configuration may contain private installation values. The inspection helper
# emits only directory paths. Reject files where a directory mount is expected.
mount_config=$(mktemp)
mount_paths=$(mktemp)
trap 'rm -f "$mount_config" "$mount_paths"' EXIT HUP INT TERM
if ! docker compose config --format json >"$mount_config"; then
    echo "Cannot resolve Compose settings. Check COMPOSE_FILE and .env." >&2
    exit 1
fi
if ! docker run --rm -i python:3.12-slim python -c "$(cat deployment/mount_directories.py)" <"$mount_config" >"$mount_paths"; then
    echo "Cannot inspect bind paths. Check Docker and image availability." >&2
    exit 1
fi
while IFS= read -r directory; do
    if [ -e "$directory" ] && [ ! -d "$directory" ]; then
        echo "Bind path is not a directory: $directory. Move the file and retry; it was not changed." >&2
        exit 1
    fi
    if ! mkdir -p "$directory"; then
        echo "Cannot create bind directory: $directory. Check host permissions." >&2
        exit 1
    fi
done <"$mount_paths"

# Validate the existing settings and mounts with the configure image. --no-deps
# prevents this check from starting database or application dependencies.
# A failed preflight stops deployment before the application restart phase.
echo "Checking .env and mounted inputs before building or restarting application services..."
if ! sh deployment/build-service.sh configure; then
    echo "Could not build the configuration checker. Check Docker and network access." >&2
    exit 1
fi
if ! docker compose run --rm --no-deps configure python /app/deployment/configure.py --check; then
    echo "Preflight failed. Fix the .env fields listed above and run ./start.sh again." >&2
    echo "Application services were not restarted. Do not replace .env with settings from another checkout." >&2
    echo "For /host_mnt mount errors, check Docker Desktop file sharing for this checkout. Do not delete data volumes." >&2
    exit 1
fi

echo "Building and starting Memstara. Existing services will restart to load .env."
if [ "$reset_execution_history" = true ]; then
    echo "Execution history reset requested. Settings and original research inputs will be retained."
else
    echo "Finish active experiments before running this command. Saved data is retained."
fi
# Separate service builds avoid concurrent BuildKit sessions on older Docker Desktop.
# Finish every image before replacing application containers.
# This ordering also keeps reset deletion behind successful image builds: a
# dependency download, compilation, or build-time check failure cannot trigger
# history cleanup. Bootstrap preparation may already have updated setup files.
for service in control initialize api web; do
    if ! sh deployment/build-service.sh "$service"; then
        echo "Image build failed. Existing services were not restarted." >&2
        exit 1
    fi
done
if [ "$reset_execution_history" = true ]; then
    # Stop the application before taking backups so its workers stop writing.
    # Leave PostgreSQL running: logical dumps require access to both databases.
    # Other external writers must also remain idle during backup and reset.
    echo "Stopping experiments and clearing execution history before startup..."
    docker compose stop control api web
    # The helper creates a unique timestamped directory for each attempt.
    # Default destination: a sibling directory outside the checkout's outputs.
    # It saves both full database dumps and an archive of outputs and settings,
    # validates archive readability, records SHA-256 checksums, and writes
    # COMPLETE.json only on success. This is not a full restore rehearsal.
    # Backups contain credentials and research results; keep them private.
    # Partial backups remain for diagnosis, and prior backups are never pruned.
    if ! python3 deployment/backup-execution-history.py --destination "${MEMSTARA_BACKUP_DIR:-../memstara-execution-backups}"; then
        echo "Backup failed. Nothing was deleted; application services remain stopped." >&2
        exit 1
    fi
    # Only a successful backup permits --apply. Mount the current cleanup
    # script read-only and run it in a disposable control container using the
    # installation's normal runtime settings. The cleanup helper checks known
    # database dependencies and limits deletion to execution records/artifacts.
    # A cleanup failure leaves the application stopped for inspection. Do not
    # assume that a failure after deletion began implies a complete rollback
    # across both databases and the filesystem; retain the verified backup.
    if ! docker compose run --rm --no-deps \
        -v "$PWD/deployment/reset-execution-history.py:/tmp/reset-execution-history.py:ro" \
        control python /tmp/reset-execution-history.py --apply; then
        echo "Cleanup did not finish. Application services remain stopped; inspect the error before restarting." >&2
        exit 1
    fi
fi
# Recreate services from the images built above. Compose handles dependency
# ordering, configuration generation, schema initialization, and health gates.
# --no-build prevents a second build after reset; --force-recreate loads the
# updated images and environment while retaining persistent volumes.
# Capture startup output so retry decisions can inspect the actual error.
startup_log=$(mktemp)
trap 'rm -f "$mount_config" "$mount_paths" "$startup_log"' EXIT HUP INT TERM
startup_attempt=0
while :; do
    if docker compose up -d --no-build --force-recreate >"$startup_log" 2>&1; then
        cat "$startup_log"
        break
    fi
    cat "$startup_log" >&2
    startup_attempt=$((startup_attempt + 1))
    # A different process can claim the tested port while images are building.
    # Retry only recognized port conflicts, with at most three startup attempts.
    # Other errors must be investigated rather than repeatedly restarting.
    if [ "$startup_attempt" -lt 3 ] && grep -Eiq \
        'address already in use|port is already allocated|port.*already.*use' "$startup_log"; then
        if sh deployment/select-web-port.sh "$preparer_image"; then
            continue
        fi
    fi
    echo "Startup failed. Correct the reported error, then run ./start.sh again." >&2
    echo "Inspect: docker compose logs --tail=80 configure initialize control api web" >&2
    exit 1
done

# Check both backends through the same proxy the browser uses, not just containers.
# A running container alone does not prove that browser-facing routes work.
# Allow up to 30 readiness checks, with two seconds between failed checks;
# total elapsed time also includes the duration of each check itself.
echo "Checking the web application and backend connections..."
attempt=0
until docker compose exec -T control python /app/deployment/check_web.py; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        echo "Services started, but application readiness could not be confirmed." >&2
        echo "Inspect: docker compose ps -a" >&2
        echo "Inspect: docker compose logs --tail=80 configure initialize control api web" >&2
        exit 1
    fi
    sleep 2
done
# Report the actual published address, which may differ from the initially
# configured port after conflict resolution. A bind address such as 0.0.0.0
# means all interfaces; remote browsers should use the server's reachable IP
# or DNS name with this port. Firewall/network reachability is not tested here.
address=$(docker compose port web 80)
printf '\nMemstara is ready: http://%s/\n' "$address"
echo "You can close this terminal. To stop: docker compose stop"
echo "No experiment or paid model request was started."
