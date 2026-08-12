# ADR-0008: Colocate the Celery worker with the API on free hosting

- **Status:** Accepted
- **Date:** 2026-08-12
- **Phase:** 2a

## Context

[ADR-0002](0002-technology-stack-selection.md) chose Celery so that slow work — PDF parsing,
and later embedding generation — runs outside the request path, in a worker process that scales
independently of the API. That design assumed the worker would be its own deployable service.

It cannot be, on the hosting we have. **Render's free tier supports only web services,
Postgres, Key Value, and static sites**; their documentation states plainly that other service
types do not support free instances. A Background Worker is a paid service type, starting at
$7/month.

This was not visible when ADR-0002 was written. It is the kind of constraint that only appears
on contact with the platform, which is an argument for having deployed the skeleton in Phase 1
rather than at the end.

Two further constraints shape the answer:

- The free web service has **512 MB of RAM**, shared by everything running in the container.
- Redis is *not* the problem: Render Key Value is available free, so the broker itself is fine.

## Decision

Run the API and the Celery worker as **two processes inside the single free web service**,
supervised by `honcho` (a Python port of foreman) reading a `Procfile`.

The worker runs with `--concurrency=1` and `--max-tasks-per-child=10`.

**Nothing in the application code knows about this.** The worker still consumes from a real
Redis queue, still uses its own synchronous database session ([ADR-0005](0005-async-sqlalchemy-with-sync-worker-path.md)),
and is still started by its own command. `docker-compose.yml` runs it as a **separate
container** locally, which is the architecture as designed. Colocation is a deployment
packaging decision, confined to `Procfile` and `start.sh`.

Moving to a dedicated worker is therefore a hosting change, not a code change: delete the
`worker:` line from the Procfile and add a `type: worker` service to `render.yaml`.

## Alternatives considered

- **Pay $7/month for a Render Background Worker.** The correct answer for anything real, and
  what a team would do without hesitation. Rejected only because the project's stated
  constraint is free-tier hosting. It remains the documented upgrade path, and the fact that
  it is a config change rather than a rewrite is the point of keeping the layers separate.
- **Deploy the worker to a different free platform** (Fly.io, Koyeb) while the API stays on
  Render. Preserves genuine process isolation for free. Rejected on operational cost: a fourth
  hosting provider, cross-provider networking to Redis and Postgres, a second deploy pipeline,
  and two dashboards to check when something breaks. That is a lot of moving parts to avoid a
  Procfile line.
- **Drop Celery and use FastAPI `BackgroundTasks`.** Would remove the problem entirely by
  removing the queue. Rejected for the reasons in ADR-0002: work that dies with the process, no
  retries, no visibility, and no independent scaling — and it would run the parse inside the API
  process anyway, which is exactly what colocation is accused of.
- **Parse synchronously in the request.** Rejected. The 202-and-poll contract is a stated
  product requirement (PRD §S2), and a multi-second request holding a worker is precisely the
  failure the queue exists to prevent.

## Consequences

**Better**

- Stays within free hosting, so the live demo a recruiter clicks actually processes resumes.
- One image, one deploy, one set of environment variables, one log stream.
- The architecture is preserved where it matters: real broker, real queue semantics, real
  separation in the code and in local development.
- `honcho` forwards SIGTERM to both children and exits when either dies, so a crashed worker
  takes the container down and the platform restarts it — rather than leaving a healthy API
  cheerfully accepting uploads that nothing will ever process.

**Worse / accepted**

- **No independent scaling.** More parsing capacity means more API instances too. Precisely the
  property ADR-0002 wanted, given up for hosting cost.
- **Memory contention is real.** A parse and an Argon2 login (64 MB) compete for the same
  512 MB. `--concurrency=1` and `--max-tasks-per-child=10` bound it; measurement in Phase 2c,
  when the embedding model lands, will decide whether the free tier remains viable at all.
- **A CPU-bound parse slows API responses**, because both processes share one small instance.
- **Crash coupling.** A worker that dies restarts the API with it. Chosen deliberately over the
  alternative — an API that looks healthy while the queue silently drains nowhere is a much
  harder failure to notice.
- `Procfile` and `start.sh` now encode a hosting workaround. Both say so in comments, and this
  ADR is the reason they say it.
