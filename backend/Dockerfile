# syntax=docker/dockerfile:1.9

# ---------------------------------------------------------------------------------------
# Stage 1 — builder. Resolves and installs dependencies into a virtualenv.
#
# Multi-stage build: the tools needed to *install* dependencies (uv, compilers) are not
# needed to *run* the app. Building in one stage and copying only the result into a clean
# second stage keeps the shipped image small and removes build tooling from the attack
# surface of what actually runs in production.
# ---------------------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Dependencies are installed before application code is copied. Docker caches each layer, so
# editing a Python file invalidates only the final COPY — not the dependency install, which
# is the slow part. Copying source first would re-resolve every dependency on every edit.
COPY pyproject.toml uv.lock* ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev

COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-dev

# Download the embedding model at BUILD time, not on first use.
#
# Render's free instance has an ephemeral disk, so a model fetched at runtime is downloaded
# again after every deploy and every cold start — ~130 MB, on the critical path of a user's
# first request. Baking it in makes the container start ready: it costs image size, which is
# free, instead of request latency, which is not.
ENV FASTEMBED_CACHE_PATH=/app/.model-cache
RUN uv run python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"


# ---------------------------------------------------------------------------------------
# Stage 2 — runtime.
# ---------------------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    # Must match the builder stage. If it does not, the runtime looks in an empty directory
    # and silently re-downloads a model the image already contains.
    FASTEMBED_CACHE_PATH=/app/.model-cache

# Run as an unprivileged user. A container process running as root that gets compromised has
# root inside the container, and that is a much shorter path to escaping it.
RUN groupadd --system --gid 1001 appuser \
    && useradd --system --uid 1001 --gid appuser --create-home appuser

WORKDIR /app

COPY --from=builder --chown=appuser:appuser /app /app

# Set the executable bit here rather than trusting git to carry it. Development happens on
# Windows, which has no POSIX permission bits, so a freshly cloned start.sh can arrive without
# +x and fail with "permission denied" — a confusing sibling of the exit-127 it replaced.
# (.gitattributes already pins *.sh to LF endings, which prevents the other classic failure:
# "bad interpreter: /bin/sh^M".)
RUN chmod +x /app/start.sh

USER appuser

EXPOSE 8000

# The image is built once and used for both the API and the Celery worker (Phase 2); only the
# command differs. One image means the code that enqueues a task is provably the same code
# that executes it.
CMD ["/app/start.sh"]
