# Engineering requirements checklist

The standards this project holds itself to. Updated at the end of every phase.

**Legend:** ✅ done · 🟡 partially done · ⬜ not started

_Last updated: end of Phase 1a_

| # | Requirement | Status | Where it lives / when |
|---|---|---|---|
| 1 | System architecture documented (diagram + written rationale) | ✅ | [architecture.md](architecture.md), [database.md](database.md), diagrams in README |
| 2 | Layered structure (routes → services → repositories), no logic in handlers | ✅ | `backend/app/` — layer import rules in [backend/README.md](../backend/README.md); services layer populated in 1b |
| 3 | A deliberate design pattern beyond MVC, explained not just used | ✅ | Repository pattern (`repositories/base.py`) + DI (`api/deps.py`), both documented inline |
| 4 | Scalable backend (stateless API, async workers) | 🟡 | Stateless async API built; Celery workers land in Phase 2 |
| 5 | Relational DB design (normalized schema, ERD, Alembic migrations) | ✅ | ERD + 3NF rationale in [database.md](database.md); first migration applied and reversible |
| 6 | Authentication + authorization (JWT, roles) | 🟡 | `users` table and `user_role` enum exist; auth flows in Phase 1b |
| 7 | REST API with OpenAPI/Swagger docs | ✅ | `/docs` + `/openapi.json`, auto-generated, disabled in production |
| 8 | Real git workflow: feature branches, PRs, conventional commits | ✅ | `main` protected by ruleset; direct pushes blocked, merge-commits only |
| 9 | Automated tests written alongside each feature | ✅ | 31 tests, unit + integration, migrations tested by the suite itself |
| 10 | CI pipeline: lint + test on every push | ✅ | `.github/workflows/ci.yml` — ruff, mypy, pytest, migration reversibility, Docker build |
| 11 | CD pipeline: auto-deploy on merge to `main` | ⬜ | Phase 1b |
| 12 | A real, working deployment with a public link | ⬜ | Phase 1b |
| 13 | Security basics: input validation, rate limiting, env-var secrets, dep scanning | 🟡 | Pydantic validation at the boundary, secrets in env vars only, non-root container, least-privilege CI token. Rate limiting + Dependabot in Phase 5 |
| 14 | Monitoring: structured logs, error tracking, health checks | 🟡 | `/health` + `/health/ready` (liveness vs readiness separated). structlog + Sentry in Phase 6 |
| 15 | Docs: README with diagram, setup instructions, ADR log | ✅ | README with working setup steps, 6 ADRs, PRD, architecture, database docs |
| 16 | A UI that looks like a product, not a template | ⬜ | Phase 4 |

## Phase 1a summary

**Newly complete:** 2, 3, 5, 7, 8, 9, 10, 15
**Advanced:** 4, 6, 13, 14
**Not started:** 11, 12, 16

### Verified, not just written

Everything claimed above was executed locally before being committed:

- `alembic upgrade head` → `downgrade base` → `upgrade head` — migration reverses cleanly
- `pytest` — 31 passed in 0.53s
- `ruff check` — clean; `ruff format --check` — clean; `mypy app` — clean, 21 files
- `docker compose build` — image builds
- `docker compose up` — stack healthy; `/health`, `/health/ready`, and `/docs` all respond
- `users` table and the `vector` extension confirmed present in the container's database

### Bugs found and fixed during Phase 1a

Kept because the fixes are documented in the code and are the sort of thing worth being able to
talk about:

1. `pydantic-settings` JSON-decodes list fields from `.env` before validators run — needed
   `NoDecode` for the comma-separated `CORS_ORIGINS`.
2. A natively installed PostgreSQL held host port 5432, so the container was reachable only
   over IPv6 and connections silently hit the wrong server. Moved to 5433.
3. SQLAlchemy's `Enum` auto-creates its PG type during `create_table`, colliding with the
   explicit `CREATE TYPE` — resolved with `create_type=False`.
4. Test and fixture event-loop scopes must both be `session`, or a session-scoped asyncpg
   engine hands connections to the wrong loop.
5. `TEST_DATABASE_URL` lives in `.env`, not the process environment, so the conftest bootstrap
   read `None` and migrations were applied to the development database.
6. SQLAlchemy persists enum *member names* by default, not values — needed `values_callable`.
