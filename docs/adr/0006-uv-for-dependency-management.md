# ADR-0006: uv for Python dependency management

- **Status:** Accepted
- **Date:** 2026-08-11
- **Phase:** 1a

## Context

Two properties matter more than raw speed here:

1. **Reproducibility.** The environment that passes tests in CI must be byte-for-byte the
   environment that runs in production. A `requirements.txt` with pinned direct dependencies
   does not achieve this: transitive dependencies are unpinned, so a patch release of something
   three levels down can appear between the CI run and the deploy.
2. **Docker build time.** Dependency resolution and install happen on every image build whose
   dependency layer is invalidated. On a free-tier CI runner this is the dominant cost, and slow
   CI is the reason people start skipping it.

## Decision

Use **uv** (Astral, the authors of ruff) for dependency resolution, locking, and virtualenv
management. `pyproject.toml` declares dependencies; `uv.lock` pins the entire resolved graph,
including transitive dependencies and hashes, and is committed.

Development dependencies live in a PEP 735 `[dependency-groups]` table, so `uv sync --no-dev`
in the Docker build installs the runtime set only — pytest and mypy never reach the production
image.

## Alternatives considered

- **pip + `requirements.txt`.** Universally understood and needs no explanation. Rejected on
  reproducibility: pinning direct dependencies leaves the transitive graph floating, and a
  separate `requirements-dev.txt` has to be kept manually in sync. `pip-tools` fixes the
  locking but adds a compile step that must be remembered.
- **Poetry.** Mature, real lockfile, several years of production use. Rejected mainly on
  resolution speed — its resolver can add minutes to a cold Docker build — and because its
  Docker story needs deliberate care to avoid shipping the whole Poetry toolchain in the
  runtime image.
- **PDM.** Standards-compliant and capable, but a smaller community and no advantage over uv
  that applies here.

## Consequences

**Better**

- `uv.lock` makes builds reproducible: the same graph resolves on a laptop, in CI, and in the
  image.
- Installs are fast enough that a cold CI cache is no longer a reason to avoid running CI.
- One tool covers virtualenv creation, resolution, locking, and running commands, replacing
  `venv` + `pip` + `pip-tools`.
- Dependency groups keep test and lint tooling out of the production image without a second
  requirements file.

**Worse / accepted**

- **Newest of the options**, so fewer existing answers when something behaves unexpectedly.
  Mitigated by uv's compatibility with standard `pyproject.toml` — abandoning it means deleting
  a lockfile, not rewriting dependency declarations.
- **Another tool to install** before the project runs. Documented as a prerequisite in the
  README, and the Docker path needs it only inside the build stage.
- The `uv` version is pinned in both the Dockerfile and the CI workflow, so **two places must
  be updated together** when it is bumped.
