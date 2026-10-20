#!/bin/sh
# Retry only recognizable Docker builder transport failures, never compilation errors.
set -eu
if [ "$#" -ne 1 ]; then
    echo "Usage: build-service.sh SERVICE" >&2
    exit 2
fi
build_log=$(mktemp)
trap 'rm -f "$build_log"' EXIT HUP INT TERM
attempt=1
while :; do
    echo "Building $1 (attempt $attempt/3); build output follows when this attempt finishes..."
    if docker compose build "$1" >"$build_log" 2>&1; then
        cat "$build_log"
        exit 0
    fi
    cat "$build_log" >&2
    if ! grep -Eq 'failed to dial gRPC|unable to upgrade to h2c|rpc error: code = Unavailable' "$build_log"; then
        echo "Build failed; this is not a recognized transient builder transport error." >&2
        exit 1
    fi
    if [ "$attempt" -ge 3 ]; then
        echo "Docker builder transport failed three times. Check Docker Desktop diagnostics; no services were restarted." >&2
        exit 1
    fi
    echo "Docker builder connection failed. Retrying this image without restarting Docker or deleting caches/volumes." >&2
    sleep "$attempt"
    attempt=$((attempt + 1))
done
