#!/bin/sh
# Run from this checkout after stopping experiments in the UI. No model request.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
test -f resources/knowledge/hiv-combined/index.md
test -f resources/knowledge/hiv-combined/addiction-kb/index.md
test -f resources/knowledge/hiv-combined/hiv-suppression/index.md

# Finish builds and real runtime validation before changing the installation policy.
sh deployment/build-service.sh control
sh deployment/build-service.sh initialize
docker compose run --rm --no-deps control python /app/deployment/check_hiv_combined.py

echo 'Stopping pipeline control to activate the new source. Existing results are retained.'
docker compose stop control
backup="user-inputs/app-selection.before-combined.json"
if [ ! -e "$backup" ]; then
    cp user-inputs/app-selection.json "$backup"
fi
mkdir -p user-inputs/hiv-combined
cp deployment/hiv-combined-research.json user-inputs/hiv-combined/research.json
cp deployment/hiv-combined-selection.json user-inputs/app-selection.json
sh start.sh
echo 'Combined HIV study registered. Select "HIV Integrated Knowledge Base" in experiment Data settings for a new execution.'
echo 'Previous studies and results remain unchanged. Do not resume an old execution with changed sources.'
