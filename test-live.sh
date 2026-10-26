#!/bin/sh
# Explicitly opt in to one paid model pipeline; never restart operating services.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
echo 'This runs one paid Haiku pipeline using the existing Docker application settings.'
echo 'The application must already be running. Existing experiments and data are retained.'
sh deployment/build-service.sh acceptance
docker compose --profile verification run --rm --no-deps acceptance
