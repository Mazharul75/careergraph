# Infrastructure

Everything needed to run CareerGraph locally and to build the images that get deployed.

## Planned contents (Phase 1)

| File | Purpose |
|---|---|
| `Dockerfile` | Multi-stage build for the backend. One image, two entrypoints (API and Celery worker). |
| `docker-compose.yml` | Local development: API, worker, Postgres+pgvector, Redis. |
| `postgres/init.sql` | Enables the `vector` extension on first container start. |

## Why one image for API and worker

If the API and the worker are built from separate images, they can drift — a deploy can update one
and not the other, and a task can be executed by code that doesn't match the code that enqueued it.
One image with two entrypoints makes that class of bug impossible.

## Status

Empty. Populated in Phase 1.
