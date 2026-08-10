# ADR-0005: Async SQLAlchemy for the API, sync sessions for workers

- **Status:** Accepted
- **Date:** 2026-08-11
- **Phase:** 1a

## Context

[ADR-0002](0002-technology-stack-selection.md) chose FastAPI partly because it is async-native.
That choice only pays off if the code actually *is* async where it matters.

A CareerGraph request spends almost all its wall-clock time waiting: on Postgres, and later on
Redis and embedding computation. That is I/O-bound work, which is exactly what an event loop is
good at — while one request waits on a query, the loop serves another. FastAPI does support
plain `def` handlers, running them in a threadpool, but that caps concurrency at the threadpool
size and spends memory on stacks that are doing nothing but blocking.

The complication is Celery. Celery workers are synchronous processes; its task model predates
asyncio and does not run an event loop per task. Async database code cannot be called from a
Celery task without wrapping every task body in `asyncio.run()`, which creates and destroys an
event loop per task and cannot share a connection pool between them.

## Decision

**The API uses SQLAlchemy 2.0's async engine with the `asyncpg` driver.** Route handlers are
`async def`, the session dependency yields an `AsyncSession`, and every repository method is
awaited.

**Celery workers (Phase 2) will get their own synchronous engine and session factory**, sharing
the same ORM models and the same migrations, but a separate `psycopg`-backed sync engine.

Models, schemas, and migrations are shared. Only the session/engine construction differs.

## Alternatives considered

- **Sync SQLAlchemy everywhere.** Simplest by a wide margin: one session factory, no greenlet
  machinery, straightforward pytest fixtures. FastAPI's threadpool makes it work correctly.
  Rejected because it undercuts the reason FastAPI was chosen — an interviewer who asks "you
  picked an async framework, did you use it?" deserves a better answer than "no". The honest
  counter-argument is that at our traffic it would make no measurable difference, and that is
  true; the deciding factor is that the async path is the one worth learning, and the costs are
  paid once during setup rather than continuously.
- **Async everywhere including workers**, wrapping each Celery task in `asyncio.run()`.
  Rejected: a fresh event loop per task means a fresh connection pool per task, so the pooling
  is defeated exactly where throughput matters most.
- **Drop Celery for an async-native queue (arq, Dramatiq).** `arq` is asyncio-first and would
  remove the split entirely. Rejected on the same grounds as ADR-0002: a much smaller ecosystem
  and far less recognition, in exchange for avoiding roughly thirty lines of sync-engine setup.
- **`asgiref.sync_to_async` bridging.** Adds a thread hop and a layer of indirection to hide a
  split that is better made explicit.

## Consequences

**Better**

- The async story is real and demonstrable, not aspirational.
- Under concurrent load the API holds far more in-flight requests per process than a threadpool
  would, which matters on a free tier with one small instance.
- The API/worker split is explicit in the code rather than an accident.

**Worse / accepted**

- **Two session factories to keep straight.** A future contributor can import the wrong one.
  Mitigated by keeping them in separate modules with unambiguous names.
- **`expire_on_commit=False` is mandatory.** SQLAlchemy's default expires attributes after
  commit, so the next attribute access silently triggers a lazy reload — which in async code
  raises `MissingGreenlet`, because implicit I/O happens outside an `await`. This is the single
  most common async-SQLAlchemy trap and the setting is documented where it is applied.
- **Lazy relationship loading is effectively banned.** Related objects must be loaded eagerly
  with `selectinload`/`joinedload`, for the same reason. In practice this is a benefit — it
  makes N+1 queries impossible to write by accident — but it is a real constraint.
- **Alembic needs custom async plumbing.** Its migration context is synchronous, so `env.py`
  opens an async connection and hands it over via `connection.run_sync(...)`.
- **Test fixtures are more delicate.** An asyncpg connection is bound to the event loop that
  created it, so a session-scoped engine requires a session-scoped event loop; mismatched
  scopes fail with "got Future attached to a different loop". Both scopes are pinned in
  `pyproject.toml` with a comment explaining why.
