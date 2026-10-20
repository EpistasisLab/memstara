#!/bin/sh
set -eu
. /settings/postgres.env
exec /usr/local/bin/docker-entrypoint.sh "$@"
