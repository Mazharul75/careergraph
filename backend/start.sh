#!/bin/sh
# Production entrypoint.
#
# This exists as a file rather than an inline command in render.yaml because an inline
# `sh -c "a && b"` gets parsed twice — once by the platform, once by the container's shell —
# and the quoted string arrives as a single command word, failing with exit 127. A script
# invoked as one bare token has nothing left for any layer to re-parse.
#
# Interpreter paths are explicit rather than relying on PATH. PATH is set correctly by the
# Dockerfile, but a hosting platform is free to override the environment, and a start command
# that fails only in production is exactly the failure worth designing out.

set -e # abort on any failure: never start a server against a half-migrated schema

echo "Applying database migrations..."
/app/.venv/bin/alembic upgrade head

# Migrations run here, in the entrypoint, rather than in either process defined in the
# Procfile. Both start concurrently, so putting `alembic upgrade` in one of them would race
# the other against a schema that does not exist yet.

echo "Starting API and worker (port ${PORT:-8000})..."
# `exec` replaces this shell with honcho, so honcho becomes PID 1 and receives SIGTERM
# directly when the platform stops the container. honcho forwards the signal to both children.
# Without it, the signal stops at /bin/sh, which does not forward, and every deploy ends in a
# hard kill after the grace period — dropping in-flight requests instead of draining them.
exec /app/.venv/bin/honcho start
