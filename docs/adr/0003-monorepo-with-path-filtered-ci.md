# ADR-0003: Monorepo with path-filtered CI

- **Status:** Accepted
- **Date:** 2026-08-06
- **Phase:** 0

## Context

CareerGraph has at least four deployable or buildable parts: the FastAPI service, the Celery worker,
the Next.js frontend, and the infrastructure definitions. They can live in one repository or several.

The project has a second purpose beyond working software: it is portfolio evidence. A recruiter or
interviewer typically spends a couple of minutes on a repository. That makes discoverability and a
single coherent commit history first-class requirements, not cosmetics.

## Decision

A single repository, `careergraph`, containing `backend/`, `frontend/`, `infra/`, and `docs/`.

CI uses **path filters** so a change under `frontend/` doesn't run pytest and a change under
`backend/` doesn't run the Next.js build. Deployments are likewise scoped: Vercel watches
`frontend/`, Render watches `backend/` and `infra/`.

## Alternatives considered

- **Separate `careergraph-api` and `careergraph-web` repositories.** This is closer to how many
  companies operate, and CI is simpler with no path filtering. Rejected on three grounds: the commit
  history splits into two thinner histories when a substantial single history is exactly what this
  project needs to show; a change spanning API and UI requires two coordinated PRs; and a recruiter
  landing on the frontend repo sees a UI with no visible system behind it.
- **Three repos (api / worker / web).** Worse still — the worker shares almost all of its code with
  the API and would need a shared package published somewhere. Real cost, no benefit at this size.
- **A monorepo tool (Nx, Turborepo, Bazel).** These solve dependency-graph-aware builds across many
  packages. With two packages, they add configuration and a learning curve for a problem we don't
  have.

## Consequences

**Better**

- One link shows the whole system: architecture docs, backend, frontend, infra, CI.
- Cross-cutting changes (add an API field, consume it in the UI) are one atomic PR.
- Shared tooling lives in one place: one `.gitignore`, one `.editorconfig`, one ADR log.
- The commit history tells one continuous story.

**Worse / accepted**

- CI needs path filters, or every frontend typo fix runs the full Python test suite. This is
  configuration we must get right in Phase 1.
- Each hosting provider must be told which subdirectory it owns — a per-provider setting that's easy
  to forget and produces confusing failures when wrong.
- The repository root has more top-level noise than a single-purpose repo.
- If the backend ever needs to be extracted, it's a `git filter-repo` operation rather than nothing.
  Judged unlikely and cheap enough.
