#!/usr/bin/env bash
# Deploy output-loading improvements without replacing the experiment controller.
# This script deliberately targets only the read-only viewer API and web UI.
# It does not run start.sh, initialize, migrations, history reset, or volume removal.
# Running experiments keep the same control container, process, image and mounts.
# Browser connections may briefly disconnect while the viewer services restart.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."

control_identity() {
    local container
    container="$(docker compose ps -q control)"
    if [[ -z "$container" ]]; then
        echo 'No running control container found. No services were changed.' >&2
        return 1
    fi
    docker inspect --format '{{.Id}} {{.State.StartedAt}}' "$container"
}

before="$(control_identity)"
echo 'Building the viewer API and web UI. Experiments remain running.'
docker compose build api web
if [[ "$(control_identity)" != "$before" ]]; then
    echo 'The controller changed during the build. Viewer deployment was not started.' >&2
    exit 1
fi

# --no-deps prevents Compose from restarting control, databases, Redis or initialize.
# Recreate web as well so nginx resolves the newly created API container address.
docker compose up -d --no-deps --force-recreate --wait --wait-timeout 120 api web
if [[ "$(control_identity)" != "$before" ]]; then
    echo 'The controller identity changed unexpectedly. Inspect it before continuing.' >&2
    exit 1
fi
echo 'Viewer deployment completed. The experiment controller was not restarted.'
echo 'Refresh the browser. Cold history summaries may need an initial preparation.'
docker compose ps api web control
