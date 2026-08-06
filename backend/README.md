# Backend

FastAPI service + Celery worker. Both run from the same codebase and the same Docker image; only the
entrypoint differs.

## Layer responsibilities

Dependencies point downward only. A layer may call the layer below it; it may never reach upward.

| Directory | Responsibility | May import | Must not import |
|---|---|---|---|
| `app/api/v1/` | HTTP: parse request, authorize, delegate, shape response | `schemas`, `services`, `core` | `models`, `repositories`, SQLAlchemy |
| `app/services/` | Business logic and orchestration | `repositories`, `core`, domain types | FastAPI, `Request`/`Response`, SQLAlchemy queries |
| `app/repositories/` | All database access, one place | `models`, SQLAlchemy | `services`, `api` |
| `app/models/` | SQLAlchemy ORM models — the tables | `db.base` | everything above |
| `app/schemas/` | Pydantic request/response contracts | — | `models` |
| `app/core/` | Config, security primitives, logging | — | `services`, `api` |
| `app/db/` | Engine, session lifecycle, declarative base | `core` | `services`, `api` |
| `app/workers/` | Celery app and task definitions | `services` | `api` |

The rule that matters most: **`schemas` and `models` are separate types.** An ORM model describes a
table; a schema describes the public API. Keeping them apart is what stops a `password_hash` column
from ever appearing in a response body.

Full reasoning: [../docs/architecture.md](../docs/architecture.md)

## Tests

- `tests/unit/` — services and graph logic against fake repositories. No database, no HTTP.
- `tests/integration/` — real Postgres and real HTTP via FastAPI's `TestClient`.

## Status

Scaffolding only. Application code, dependencies, and Dockerfile arrive in Phase 1.
