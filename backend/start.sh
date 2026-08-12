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

echo "Starting API on port ${PORT:-8000}..."
# `exec` replaces this shell with uvicorn, so uvicorn becomes PID 1 and receives SIGTERM
# directly when the platform stops the container. Without it, the signal goes to /bin/sh,
# which does not forward it, and every deploy ends in a hard kill after the grace period —
# dropping in-flight requests instead of draining them.
#
# --proxy-headers and --forwarded-allow-ips are required behind a load balancer. Without them
# every request appears to originate from the proxy, so client IPs are wrong and generated
# URLs use http:// even though the connection was HTTPS.
exec /app/.venv/bin/uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "${PORT:-8000}" \
  --proxy-headers \
  --forwarded-allow-ips='*'
