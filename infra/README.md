# Infrastructure

## Where things live

| File | Purpose |
|---|---|
| [`../docker-compose.yml`](../docker-compose.yml) | Local stack: Postgres+pgvector, Redis, API. At the repository root so `docker compose up` works from where you cloned. |
| [`../backend/Dockerfile`](../backend/Dockerfile) | Multi-stage build for the backend. Lives beside the code it builds so the build context is just `backend/`. |
| [`postgres/init.sql`](postgres/init.sql) | Creates the separate test database on first container start. |

Deployment configuration (Render, Neon) lands here in Phase 1b.

## One image, two entrypoints

The same image runs the API and, from Phase 2, the Celery worker — only the command differs.
If they were separate images they could drift, and a deploy could update one but not the other,
leaving a task executed by code that doesn't match the code that enqueued it. One image makes
that class of bug impossible.

## Host ports are non-default

Postgres publishes on **5433** and Redis on **6380**. A natively installed PostgreSQL commonly
already owns 5432, and Docker will still start happily — connections to `localhost` just
silently reach the other server and fail with "password authentication failed", which reads
like a credentials bug rather than a port collision. Override via `POSTGRES_HOST_PORT` and
`REDIS_HOST_PORT` in `.env`.

Inside the compose network, services reach each other by service name on default ports
(`db:5432`, `redis:6379`) — the remapping is host-side only.

## The vector extension

`CREATE EXTENSION vector` lives in the **first Alembic migration**, not in `init.sql`. Anything
configured only in compose is a step someone has to remember to repeat on Neon; putting it in a
migration means the extension exists identically on a laptop, in CI, and in production.
