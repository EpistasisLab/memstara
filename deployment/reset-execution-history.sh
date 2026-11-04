#!/bin/sh
# Compatibility entry point. Startup owns cleanup ordering and health checks.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
exec sh ./start.sh --reset-execution-history
