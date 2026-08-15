# ADR-0011: Hand-rolled fixed-window rate limiting in Redis

- **Status:** Accepted
- **Date:** 2026-08-15
- **Phase:** 5

## Context

The unauthenticated credential endpoints (`/auth/login`, `/auth/register`, `/auth/refresh`)
are the API's free attack surface: anyone on the internet can hit them, and each login
attempt costs us an Argon2 verification (~50 ms of deliberate CPU work) while costing the
attacker nothing. Argon2's cost slows a brute force but is not a *control* — nothing today
says "no" to the ten-thousandth guess. Requirement 13 calls for real rate limiting.

Constraints that shaped the decision:

- The API already runs Redis (Celery broker), and the readiness probe already treats Redis
  as a **non-critical** dependency: down means degraded, not dead.
- Adding a Python dependency forces a Docker image rebuild and grows the surface of code we
  cannot explain line by line — and explaining every line is an explicit goal of this
  project.
- CI has no Redis service, so tests must not require one.
- The service runs single-instance today but must not bake that assumption in (ADR-0008
  documents the path to a second instance).

## Decision

Implement a **fixed-window counter in Redis** (`INCR` + `EXPIRE`, ~40 lines), behind the
same `Protocol` seam the repositories use, applied per client IP to the three credential
endpoints via per-route FastAPI dependencies. Limits live in `Settings` like every other
tunable. The limiter **fails open**: if Redis is unreachable, requests pass and the outage
is surfaced by `/health/ready`, consistent with Redis's established non-critical status.
An `InMemoryRateLimiter` twin of the same algorithm serves tests and Redis-less local runs.

## Alternatives considered

- **slowapi** — the most common FastAPI limiter. Rejected: a new dependency (Docker
  rebuild), a decorator-based API that bypasses the dependency-injection seam every other
  cross-cutting concern here uses, and its in-memory default storage silently breaks the
  moment a second instance exists. Configuring it for Redis ends up writing as much code as
  the limiter itself.
- **fastapi-limiter** — requires Redis at startup and fails closed when it is missing,
  contradicting the readiness probe's decision that Redis down must degrade, not disable.
- **Sliding-window or token-bucket algorithm** — more accurate at window boundaries (a
  fixed window allows up to 2× the limit across a boundary burst). Rejected as complexity
  without a threat model: doubling 10 login attempts to 20 per boundary does not change the
  economics of guessing an Argon2-hashed passphrase. Worth revisiting only if limits ever
  meter paid API usage, where accuracy is money.
- **Nginx / platform-level limiting** — the right layer in a bigger system, but Render's
  free tier exposes no such knob, and a control that exists only in production cannot be
  tested in CI.

## Consequences

- Brute-forcing a password now costs at most `limit` attempts per window per IP address, on
  top of Argon2's per-attempt cost.
- The 429 response carries `Retry-After`, so legitimate clients (and the frontend) can back
  off precisely instead of hammering.
- A distributed attacker with many IPs is *not* stopped — per-IP limiting raises the price
  of attack, it does not eliminate it. Account-keyed lockout was deliberately avoided: it
  lets an attacker lock a victim out of their own account by guessing wrong on purpose.
- The boundary-burst weakness of fixed windows is accepted and documented above.
- Uvicorn's `--proxy-headers` (already in the Procfile) is now load-bearing for security:
  without it every client behind Render's proxy shares one IP and one bucket.
