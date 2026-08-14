# CareerGraph — working agreement

**Read [`docs/PROJECT_STATE.md`](docs/PROJECT_STATE.md) before your first reply in any session.**
It holds the live phase status, the decision log, and the accumulated gotchas. This file holds
the rules that do not change; that one holds everything that does.

**At the end of every phase, update `docs/PROJECT_STATE.md` before writing the wrap-up.** A
session that ends without updating it has lost work, even if the code is committed.

---

## Who you are working with

MD Mazharul Islam Nabil — final-year BSc CSE at AIUB (CGPA 3.97, graduating January 2027).

- **Strong at:** Python, FastAPI, Docker, SQL, OOP, algorithms, graph theory, ML/NLP coursework.
- **Has never shipped:** production auth, CI/CD, background workers, monitoring. This project
  exists to close exactly that gap.
- **Goal:** a deployed, defensible system for internship interviews — one he can explain line by
  line.

### How to explain

- Define a tool or concept the **first time** it appears — 2–3 sentences plus an analogy. Celery,
  JWT, pgvector, repository pattern, rate limiting, HNSW, topological sort all qualify.
- Do **not** explain things a CS degree covers: loops, foreign keys, recursion, Big-O notation.
- Give the **why before the what**.
- After anything non-obvious, add a one-line **"Why this matters in an interview:"** note.
- Never hide trade-offs. Name the alternative you rejected and why.

---

## Hard constraints — these have caused real problems

### 1. Never touch his GitHub

He said this explicitly and it stands:

> DO NOT attempt to access my GitHub, run gh CLI commands, or run git push directly.

- ❌ `gh` CLI, `git push`, `git pull`, `git fetch` — anything reaching the remote
- ✅ Local reads (`git status`, `git log`, `git diff`, `git branch`) are fine
- ✅ Creating files, running tests, Docker, local verification
- **Hand him exact commands to run himself.**

### 2. He runs `cmd.exe`, not bash

His prompt is `D:\PProject>`. Commands you give him must be cmd-safe:

- ❌ `cd /d/PProject && git add x` — bash syntax, fails with `&& was unexpected at this time`
- ✅ One command per line, no `cd` prefix (he is already in `D:\PProject`)

Your own tooling is different: the Bash tool is Git Bash and uses `/d/PProject`.

### 3. `git status --short` must be empty before he pushes

**Three CI failures came from incomplete `git add`.** Listing individual files is error-prone —
prefer directories, and always end a commit batch with:

```bash
git status --short
```

If it prints anything, the tree you tested is not the tree he is pushing.

### 4. Verify before claiming

Never say something works without running it. Every phase so far has been verified against a
live stack — real Postgres, real Redis, real worker, real browser. Untested code is not a
deliverable. If something is blocked, say so plainly and finish everything else.

---

## Interaction protocol

- **One phase per response.** Stop at the end of each. If a phase is too big to do well, say so
  and propose splitting it — do not quietly cut corners.
- Ask before any non-trivial architectural decision not already fixed by an ADR. Use
  `AskUserQuestion`, put the recommendation first, label it `(Recommended)`, and be honest about
  the cost of each option.
- **Every phase ends with:** files changed (full paths), the updated checklist, an interview
  recap, exact commit messages, and any manual steps spelled out step by step.
- He asked for speed in later phases: skip the ceremony, keep the verification.

---

## The machine

| Thing | Value |
|---|---|
| Repo root | `D:\PProject` (Bash tool sees `/d/PProject`) |
| OS | Windows 11 Home, shell is `cmd.exe` |
| `uv` | `C:\Users\user\.local\bin\uv.exe` — **export `PATH="/c/Users/user/.local/bin:$PATH"` first** |
| Docker CLI | `C:\Users\user\AppData\Local\Programs\DockerDesktop\resources\bin` (per-user install) |
| Docker Desktop | **Must be started manually from the desktop.** Launching it from a background shell does not persist. |
| Postgres | host port **5433** (not 5432 — a native PostgreSQL 18 service owns that) |
| Redis | host port **6380** |
| Node | v24, npm 11 |

### Commands that work

```bash
export PATH="/c/Users/user/.local/bin:$PATH"   # every Bash tool call that uses uv
cd /d/PProject/backend && uv run pytest -q
cd /d/PProject/backend && uv run ruff check . && uv run ruff format --check . && uv run mypy app tests
cd /d/PProject/backend && uv run alembic upgrade head
cd /d/PProject/frontend && npx tsc --noEmit && npx eslint . && npm run build
```

Docker (PowerShell tool, since the Bash tool cannot reach `localhost` HTTP):

```powershell
$env:Path = "C:\Users\user\AppData\Local\Programs\DockerDesktop\resources\bin;$env:Path"
Set-Location D:\PProject
docker compose up -d db redis api
```

### Tooling quirks that have bitten

- **Bash heredocs mangle apostrophes and f-strings.** Two files were corrupted this way. Use the
  **Write tool** for any file containing quotes or `${}`.
- **The Bash tool cannot reach `localhost` HTTP** (sandboxed network). Use PowerShell +
  `Invoke-RestMethod`, or `curl.exe` for multipart uploads.
- `Invoke-WebRequest` needs `-UseBasicParsing` in non-interactive PowerShell.
- Adding a Python dependency **requires `docker compose build api`** — the compose volume mounts
  code but the venv lives in the image.

---

## Where everything is

```
D:\PProject
├── CLAUDE.md                  ← this file (auto-loaded)
├── docs/
│   ├── PROJECT_STATE.md       ← READ FIRST, UPDATE EVERY PHASE
│   ├── PRD.md                 problem, users, goals, non-goals, success criteria
│   ├── architecture.md        layering rules, request lifecycle, async design
│   ├── database.md            ERD, normalization rationale, migration conventions
│   ├── CHECKLIST.md           the 16 requirements, tracked per phase
│   └── adr/                   10 ADRs — read the index before proposing a change
├── backend/
│   ├── app/
│   │   ├── api/               HTTP only: parse, authorize, delegate, shape
│   │   ├── core/              config.py (all settings), security.py (hashing, JWT)
│   │   ├── db/                base.py, session.py (async), sync_session.py (worker)
│   │   ├── models/            SQLAlchemy ORM
│   │   ├── repositories/      every query; protocols.py holds the interfaces
│   │   ├── schemas/           Pydantic request/response contracts
│   │   ├── services/          business logic — no FastAPI, no SQLAlchemy
│   │   ├── workers/           Celery app, tasks, dispatcher
│   │   └── data/              seed vocabulary + prerequisite edges
│   ├── alembic/versions/      7 migrations, all reversible
│   └── tests/{unit,integration}/
├── frontend/src/{app,lib,components}/
├── docker-compose.yml         db, redis, api, worker
├── render.yaml                Render blueprint
└── .github/workflows/         ci.yml, cd.yml
```

### Layering rule — enforced, not aspirational

`api → services → repositories → models`. Dependencies point **downward only**.

- `services/` must never import FastAPI or SQLAlchemy. It depends on `Protocol`s from
  `repositories/protocols.py`, which is what lets it be unit-tested against in-memory fakes.
- `mypy app tests` covers **tests too** — a Protocol gaining a method must fail type-checking,
  not surface as a runtime `AttributeError`. That has already happened once.
