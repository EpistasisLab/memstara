#!/bin/sh
# Probe Docker's actual host publisher, including Docker Desktop; no host Python needed.
set -eu
image=$1
scratch=$(mktemp -d)
cleanup() {
    if [ -s "$scratch/probe.cid" ]; then
        docker rm -f "$(cat "$scratch/probe.cid")" >/dev/null 2>&1 || true
    fi
    rm -rf "$scratch"
}
trap cleanup EXIT HUP INT TERM

docker compose config --format json >"$scratch/compose.json"
requested=$(docker run --rm -i "$image" python /app/deployment/web_port.py requested <"$scratch/compose.json")
current=''
if [ -n "$(docker compose ps --status running -q web 2>/dev/null)" ]; then
    current=$(docker compose port web 80 2>/dev/null || true)
fi
if [ "$current" = "127.0.0.1:$requested" ]; then
    # This project's own publisher is replaced by Compose; it is not a conflict.
    exit 0
fi

probe() {
    docker create --cidfile "$scratch/probe.cid" --publish "$1" \
        "$image" python -c 'import time; time.sleep(120)' >/dev/null || return 1
    docker start "$(cat "$scratch/probe.cid")" >"$scratch/start.log" 2>&1
}
# Some Docker Desktop versions accept a duplicate binding during container start.
# Check existing publishers explicitly as well as probing native host listeners.
docker ps --format '{{.Ports}}' >"$scratch/publishers"
if ! grep -Eq "(127\\.0\\.0\\.1|0\\.0\\.0\\.0|\\[::\\]):${requested}->" "$scratch/publishers"; then
    if probe "127.0.0.1:$requested:80"; then
        exit 0
    fi
    if ! grep -Eiq 'address already in use|port is already allocated|port.*already.*use' "$scratch/start.log"; then
        cat "$scratch/start.log" >&2
        exit 1
    fi
    docker rm -f "$(cat "$scratch/probe.cid")" >/dev/null
    rm "$scratch/probe.cid"
fi
# Let Docker allocate an available host port rather than guessing the next number.
if ! probe '127.0.0.1::80'; then
    cat "$scratch/start.log" >&2
    exit 1
fi
address=$(docker port "$(cat "$scratch/probe.cid")" 80/tcp)
selected=${address##*:}
docker run --rm --user "$(id -u):$(id -g)" \
    --mount "type=bind,source=$(pwd),target=/project" "$image" \
    python /app/deployment/web_port.py save /project "$selected"
echo "Port $requested is in use. Saved available web port $selected in .env."
