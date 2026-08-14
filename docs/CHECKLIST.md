# Engineering requirements checklist

The standards this project holds itself to. Updated at the end of every phase.

**Legend:** ✅ done · 🟡 partially done · ⬜ not started

_Last updated: end of Phase 4_

| # | Requirement | Status | Where it lives / when |
|---|---|---|---|
| 1 | System architecture documented (diagram + written rationale) | ✅ | [architecture.md](architecture.md), [database.md](database.md), diagrams in README |
| 2 | Layered structure (routes → services → repositories), no logic in handlers | ✅ | `AuthService` holds every auth rule; route handlers only call it |
| 3 | A deliberate design pattern beyond MVC, explained not just used | ✅ | Repository pattern behind `Protocol`s + DI + a narrowed `UnitOfWork`; service tests run on fakes with no database |
| 4 | Scalable backend (stateless API, async workers) | ✅ | Stateless JWT auth plus a real Celery worker consuming from Redis. Colocated on free hosting ([ADR-0008](adr/0008-colocated-celery-worker.md)); splitting it out is a config change |
| 5 | Relational DB design (normalized schema, ERD, Alembic migrations) | ✅ | Two migrations, both reversible and verified in CI |
| 6 | Authentication + authorization (JWT, roles) | ✅ | Argon2id, JWT access tokens, opaque rotating refresh tokens with reuse detection, `require_role` |
| 7 | REST API with OpenAPI/Swagger docs | ✅ | All five auth routes documented with response codes |
| 8 | Real git workflow: feature branches, PRs, conventional commits | ✅ | `main` protected; CI is now a **required** status check, so red cannot merge |
| 9 | Automated tests written alongside each feature | ✅ | 185 tests. The Celery task is executed for real against the database, not mocked |
| 10 | CI pipeline: lint + test on every push | ✅ | ruff, mypy, pytest, migration reversibility, Docker build |
| 11 | CD pipeline: auto-deploy on merge to `main` | 🟡 | `.github/workflows/cd.yml` written and gated on CI; goes live once the Render hook is set |
| 12 | A real, working deployment with a public link | 🟡 | `render.yaml` blueprint committed; needs the manual account setup below |
| 13 | Security basics: input validation, rate limiting, env-var secrets, dep scanning | 🟡 | Validation, `SecretStr`, production secret-strength check, non-root container, no plaintext credentials stored. **Rate limiting and Dependabot in Phase 5** |
| 14 | Monitoring: structured logs, error tracking, health checks | 🟡 | `/health` + `/health/ready`. structlog + Sentry in Phase 6 |
| 15 | Docs: README with diagram, setup instructions, ADR log | ✅ | 7 ADRs, PRD, architecture, database docs |
| 16 | A UI that looks like a product, not a template | ✅ | Next.js 16 dashboard with a deliberate token palette, a small primitive set, skill-gap radar, and the learning path drawn as an ordered spine |

## Phase 2a summary

**Newly complete:** 4 (async workers now real)
**Extended:** 7 (four resume routes), 9 (119 → 185 tests), 13 (upload validation), 15 (ADR-0008)

### Verified, not just written

The async pipeline was exercised against a live stack — Postgres, Redis, API, and a real Celery
worker in a separate container:

```
UPLOAD    responded in 638 ms, status=pending
POLL      t+0ms pending  →  t+1500ms processing  →  t+1750ms complete
TEXT      64 characters: "Ada Lovelace - Backend Engineer - Python PostgreSQL Docker Redis"
WORKER    Task resumes.parse[009d80f9] succeeded in 1.45s: 'complete'
DATABASE  status=complete | bytes_discarded=t | text_len=64
```

The upload returned in well under a second while the parse took 1.45 s in the worker — the
whole point of the queue, demonstrated rather than asserted.

### Phase 2a gaps, deliberately deferred

| Gap | Why acceptable | When |
|---|---|---|
| A resume can stick in `pending` if the process dies between commit and enqueue | Recoverable, and strictly better than losing the upload | Sweeper job, Phase 6 |
| No per-user upload rate limit beyond 3 concurrent pending | Fairness bound is in place; true rate limiting is a cross-cutting concern | Phase 5 |
| Worker shares 512 MB with the API | Bounded by `--concurrency=1` and child recycling | Re-measure in 2c when the embedding model lands |
| `.doc` (pre-2007 binary) unsupported | Fails loudly rather than extracting garbage | Not planned |

## Phase 1b summary

**Newly complete:** 6, 7 (extended), 9 (extended)
**Advanced:** 11, 12, 13
**Remaining:** 16, plus the Phase 5/6 halves of 13 and 14

### Verified, not just written

- 119 tests pass; migrations apply, reverse, and reapply
- ruff, `ruff format --check`, and mypy all clean
- Live smoke test against the running stack confirmed: registration, duplicate rejection (409),
  login, protected route, rotation, **reuse detection revoking the whole family**, and
  identical responses for a wrong password vs. an unknown account
- Rotation chain inspected directly in Postgres: both tokens revoked, `replaced_by_id` linked
- Stored credential confirmed to be an `$argon2id$` hash, never plaintext

### Known gaps, deliberately deferred

| Gap | Why it's acceptable now | When |
|---|---|---|
| No rate limiting on `/auth/login` | Brute force is bounded by Argon2's ~50 ms cost, but that is not a control | Phase 5 |
| Registration reveals whether an address is taken | The alternative needs email delivery we don't have | Documented in [ADR-0007](adr/0007-opaque-rotating-refresh-tokens.md) |
| `refresh_tokens` grows without bound | Spent rows must persist for reuse detection to work | Cleanup job, Phase 6 |
| Refresh token is XSS-exposed on the client | Bounded by 15-min access tokens plus reuse detection; cookies are unusable cross-domain | [ADR-0007](adr/0007-opaque-rotating-refresh-tokens.md) |
| No password reset flow | Requires email delivery; out of scope per the PRD | Not planned |
