#!/bin/sh
# Start the complete application using only Docker and the project .env.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

if [ "$#" -ne 0 ]; then
    echo "Usage: ./start.sh" >&2
    exit 2
fi
if [ ! -f .env ]; then
    (umask 077; cp .env.example .env)
    echo "Created .env. Edit the model deployment and credentials, then run ./start.sh again."
    echo "No services were started."
    exit 1
fi
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

echo "Checking .env and mounted inputs before building or restarting application services..."
if ! docker compose build configure; then
    echo "Could not build the configuration checker. Check Docker and network access." >&2
    exit 1
fi
if ! docker compose run --rm --no-deps configure python /app/deployment/configure.py --check; then
    echo "Preflight failed. Fix the .env fields listed above and run ./start.sh again." >&2
    echo "Application services were not restarted. Do not replace .env with settings from another checkout." >&2
    exit 1
fi

echo "Building and starting Memstara. Existing services will restart to load .env."
echo "Finish active experiments before running this command. Saved data is retained."
if ! docker compose up -d --build --force-recreate; then
    echo "Startup failed. Correct the reported error, then run ./start.sh again." >&2
    echo "Inspect: docker compose logs --tail=80 configure initialize control api web" >&2
    exit 1
fi

# Check both backends through the same proxy the browser uses, not just containers.
echo "Checking the web application and backend connections..."
attempt=0
until docker compose exec -T web sh -c \
    'wget -q -T 5 -O /dev/null http://127.0.0.1/ && wget -q -T 5 -O /dev/null http://127.0.0.1/control/health && wget -q -T 5 -O /dev/null http://127.0.0.1/api/discovery/questions' >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        echo "Services started, but application readiness could not be confirmed." >&2
        echo "Inspect: docker compose ps -a" >&2
        echo "Inspect: docker compose logs --tail=80 configure initialize control api web" >&2
        exit 1
    fi
    sleep 2
done
address=$(docker compose port web 80)
printf '\nMemstara is ready: http://%s/\n' "$address"
echo "You can close this terminal. To stop: docker compose stop"
echo "No experiment or paid model request was started."
