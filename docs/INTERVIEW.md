# Interview preparation — questions this project will attract, and honest answers

Every answer below is true of the actual code. Do not memorize them — read the referenced
files until you could have written the answer yourself. The strongest signal in an interview
is *"I chose X over Y because Z, and here's the trade-off I accepted."*

## Architecture

**"Walk me through what happens when a user uploads a resume."**
Request hits FastAPI → auth dependency verifies the JWT → the route validates size/type and
delegates to the resume service → service stores the row (`status=pending`) via the repository
→ commits → *then* enqueues a Celery task → returns 202 with the resume ID. The worker picks
the message off Redis, extracts text, matches skills against the vocabulary, computes an
embedding, sets `status=complete`, and drops the original bytes. The UI polls the status.
(Files: `api/v1/resumes.py` → `services/resume.py` → `workers/tasks.py`.)

**"Why commit before enqueueing? What can go wrong?"**
The task might reach the worker before the row exists — a race we would lose. Commit-first
closes that but opens the opposite gap: crash *between* commit and enqueue leaves a row
`pending` forever. That gap is closed by a beat-scheduled sweeper that re-enqueues anything
pending past 15 minutes (`workers/maintenance.py`). The textbook fix is a transactional outbox;
at this scale the sweeper achieves the same guarantee with far less machinery. Knowing the
name of the pattern you *didn't* need is the flex here.

**"Why is the API async but the worker sync?"** (ADR-0005)
The API is I/O-bound waiting on Postgres/Redis, so one process serves many concurrent requests
with an event loop. Celery workers have no event loop and each runs one task at a time, so
async buys nothing there — instead they use a synchronous engine over the same models. One
codebase, two session factories, and a hard rule that `sync_session` is never imported by API
code (a sync query in an async handler blocks *every* in-flight request).

**"Why the repository pattern? Isn't it overkill?"**
Services depend on `Protocol` interfaces, not SQLAlchemy — so business logic unit-tests run
against in-memory fakes with zero database, and mypy (which covers tests too) fails the build
if a Protocol and its implementation drift. The honest cost: more files, and an interface tax
for every new query. At this size, worth it mainly as a demonstration of testable layering.

## Auth

**"Why JWT plus refresh tokens rather than sessions?"**
Access tokens are stateless (15 min — the theft window we accept, since a JWT can't be
revoked), refresh tokens are stateful rows that rotate on every use. A spent token presented
again means theft: the whole token *family* is revoked, ejecting the thief and the user, who
just logs in again. Server-side sessions would also have worked — the JWT choice is partly
about demonstrating the harder, more common industry pattern. (`services/auth.py`,
`models/refresh_token.py`.)

**"How do you rate-limit login, and why fixed window?"** (ADR-0011)
Per-IP counters in Redis: `INCR` + `EXPIRE` per window, ~40 lines, no dependency. A fixed
window allows a burst at the boundary (up to 2× the limit) — acceptable when the limit exists
to stop *millions* of brute-force attempts, not 20. The limiter **fails open**: if Redis dies,
logins still work, because an availability outage shouldn't lock every user out; the readiness
probe surfaces the Redis outage separately.

## Data

**"Why pgvector instead of a vector database?"** (ADR-0009 area)
Embeddings live next to the rows they describe; similarity search is one SQL join away, in
the same transaction, with the same backups. A dedicated vector DB adds an operational
dependency and a consistency boundary for zero benefit at thousands of vectors. The index is
HNSW — approximate nearest neighbour; exact search would also be fine at this scale, so this
is future-proofing that cost one line.

**"How does the learning path actually work?"**
Skills form a DAG (edge = prerequisite). Gap = job's required skills minus user's confirmed
skills, expanded to include missing transitive prerequisites; a topological sort over that
subgraph yields the order. Cycles are rejected at seed time — a cyclic prerequisite graph is
a data bug, not a runtime condition to tolerate.

## Operations

**"What happens if the worker dies mid-task?"**
`task_acks_late=True`: the message is only acknowledged after the task finishes, so a killed
worker's message is redelivered. That means tasks can run twice, which is why every task is
idempotent — `parse_resume` checks for `complete` and exits. Prefetch is 1 so a crash re-runs
one task, not a buffer of them.

**"How would you debug a production 500?"**
Every response carries `X-Request-ID`; every log line of that request carries the same ID
(structlog contextvars). Logs are JSON in production, so the platform can filter on it
directly. Unhandled exceptions also land in Sentry grouped by stack trace. Flow: user reports
→ request ID from their response → filtered logs → Sentry issue for the traceback.

**"Your deploy pipeline — why not let Render auto-deploy main?"**
Render watching the branch would ship commits whose CI is still running (or red). Instead CD
triggers via `workflow_run` only after CI succeeds, calls a deploy hook, then *polls the
health endpoint* — a deploy that crashes on boot fails the pipeline visibly. Migrations run
on boot (`start.sh`), acceptable because `alembic upgrade head` is idempotent; the paid-tier
answer is a pre-deploy step.

**"Where does this design break at 100× the load?"**
Honest list: (1) embedded celery beat fires per worker instance — must move to its own process
before scaling workers; (2) API and worker share one 512 MB instance — split per ADR-0008,
which is a `render.yaml` change, not a code change; (3) per-IP rate limiting is weak behind
shared NATs; (4) the skills vocabulary is curated and static — real scale needs an NER model;
(5) Postgres connection caps arrive before CPU does — pgbouncer next.

## Things to volunteer if asked "what would you do differently?"

- **No E2E browser tests** — Playwright against the compose stack is the known gap.
- **Embedding model in-process** (~200 MB) forced `max_tasks_per_child=1`; a paid tier would
  move inference behind its own service so workers stay small.
- **The frontend polls** for parse status; websockets or SSE would push instead. Polling was
  chosen because it is stateless and survives free-tier instance restarts.
