# Contributing to CareerGraph

This is currently a solo project, but it follows a team workflow on purpose. The rules below are the
practical form of [ADR-0004](docs/adr/0004-trunk-based-branching-with-pull-requests.md).

---

## Branching model

`main` is the trunk. It is always deployable, protected, and never pushed to directly.

All work happens on short-lived branches:

```
<type>/<short-kebab-description>
```

| Type | Use for |
|---|---|
| `feat` | A new user-facing capability |
| `fix` | A bug fix |
| `refactor` | Restructuring with no behaviour change |
| `test` | Adding or fixing tests only |
| `docs` | Documentation, ADRs, README |
| `chore` | Tooling, dependencies, config |
| `ci` | CI/CD pipeline changes |
| `perf` | Performance work |

Examples: `feat/jwt-refresh-rotation`, `fix/resume-upload-mime-check`, `ci/path-filtered-workflows`.

Keep branches under a day of work where possible. Long branches drift and hide code from CI.

## Commit messages — Conventional Commits

```
<type>(<scope>): <subject>

<optional body — explain WHY, not what; the diff shows what>

<optional footer — BREAKING CHANGE: ..., Closes #12>
```

Rules:

- `type` is from the table above.
- `scope` is the area touched: `auth`, `resumes`, `jobs`, `graph`, `db`, `ci`, `docker`, `web`.
- `subject` is imperative mood, lowercase, no trailing period, ≤ 72 characters.
  Write it so it completes the sentence *"If applied, this commit will…"*.

Good:

```
feat(auth): rotate refresh tokens on every use

Single-use refresh tokens mean a stolen token breaks the legitimate
session on next refresh, making theft detectable. Old tokens are marked
revoked rather than deleted so reuse can be logged.
```

Bad: `updated stuff`, `fix`, `WIP`, `Added the new authentication system and also fixed the tests.`

**Commit in meaningful units.** A commit should be one coherent step that leaves the tree working.
Not one commit per file, and not one commit per week.

## Pull requests

Every change goes through a PR, including solo work.

1. Branch off an up-to-date `main`.
2. Commit as you go, tests alongside the code — not in a separate "add tests" commit at the end.
3. Push and open a PR using the template.
4. CI must be green. A red PR does not get merged; the fix goes on the same branch.
5. Merge with `--no-ff` so the branch topology survives in the history.
6. Delete the branch after merge.

```bash
git checkout main && git pull && git checkout -b feat/thing
```

```bash
gh pr create --fill && gh pr merge --merge --delete-branch
```

## Tests

Tests are written **with** the feature, in the same PR. A PR that adds behaviour without a test that
exercises it will not be merged.

- `backend/tests/unit/` — services and graph logic. No database, no HTTP. Fast.
- `backend/tests/integration/` — real database and real HTTP through FastAPI's `TestClient`.

## Code style

Enforced by CI, so it is not a matter of opinion:

- **Python** — `ruff` for linting and formatting, `mypy` for type checking. Type hints on all public
  functions.
- **TypeScript** — `eslint` + `prettier`.

Tooling configuration lands in Phase 1.

## Secrets

Never commit a secret. Not in code, not in a config file, not in a test fixture, not "temporarily".

- Real values live in `.env`, which is git-ignored.
- `.env.example` is committed and lists every required variable with a **placeholder** value.
- If a secret is ever committed, rotate it immediately — removing it from history is not enough,
  because it is already in every clone and in GitHub's reflog.
