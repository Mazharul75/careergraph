# Architecture Decision Records

An **ADR** is a short document that captures one significant decision, the context that forced it,
and the consequences accepted. The point is that six months later — or in an interview — the
reasoning is recoverable, not reconstructed from memory.

Rules for this log:

- One decision per file. Numbered sequentially, never renumbered.
- **ADRs are immutable once accepted.** If a decision changes, write a new ADR that supersedes the
  old one and mark the old one `Superseded by ADR-NNNN`. Editing history away defeats the purpose.
- Record the alternatives rejected and *why*. An ADR without rejected alternatives is a description,
  not a decision.

## Index

| # | Title | Status |
|---|---|---|
| [0001](0001-record-architecture-decisions.md) | Record architecture decisions | Accepted |
| [0002](0002-technology-stack-selection.md) | Technology stack selection | Accepted |
| [0003](0003-monorepo-with-path-filtered-ci.md) | Monorepo with path-filtered CI | Accepted |
| [0004](0004-trunk-based-branching-with-pull-requests.md) | Trunk-based branching with pull requests | Accepted |
| [0005](0005-async-sqlalchemy-with-sync-worker-path.md) | Async SQLAlchemy for the API, sync sessions for workers | Accepted |
| [0006](0006-uv-for-dependency-management.md) | uv for Python dependency management | Accepted |
| [0007](0007-opaque-rotating-refresh-tokens.md) | Opaque rotating refresh tokens with reuse detection | Accepted |
| [0008](0008-colocated-celery-worker.md) | Colocate the Celery worker with the API on free hosting | Accepted |
| [0009](0009-fastembed-onnx-for-embeddings.md) | fastembed (ONNX) for embeddings, with per-task worker recycling | Accepted |
| [0010](0010-skill-graph-as-a-dag.md) | Model skills as a DAG and plan with topological sort | Accepted |
| [0011](0011-hand-rolled-redis-rate-limiting.md) | Hand-rolled fixed-window rate limiting in Redis | Accepted |
| [0012](0012-embedding-as-a-separate-task.md) | Embedding runs as its own task, after the parse commits | Accepted |

## Template

```markdown
# ADR-NNNN: <short title>

- **Status:** Proposed | Accepted | Superseded by ADR-NNNN
- **Date:** YYYY-MM-DD
- **Phase:** N

## Context
What forces us to decide? Constraints, requirements, things we've learned.

## Decision
What we are doing. Stated in the active voice.

## Alternatives considered
Each option, with the concrete reason it lost.

## Consequences
What gets better, what gets worse, what we now have to live with.
```
