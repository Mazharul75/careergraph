# ADR-0002: Technology stack selection

- **Status:** Accepted
- **Date:** 2026-08-06
- **Phase:** 0

## Context

CareerGraph needs to do four things that pull in different directions:

1. Serve a normal authenticated REST API with relational data.
2. Store and search **vector embeddings** for semantic matching.
3. Run **slow work** (PDF parsing, embedding generation) off the request path.
4. Run **graph algorithms** over a skill-prerequisite DAG.

Additional constraints, which matter as much as the technical ones:

- **Free-tier hosting only.** No budget. This rules out anything requiring a paid managed service or
  a machine with lots of RAM.
- **Solo developer.** Operational burden is the scarcest resource. Every additional datastore is
  something to provision, back up, monitor, and explain.
- **The system must be defensible in an interview.** Choices should be mainstream enough that an
  interviewer recognises them, and justified well enough that "why not X?" has an answer.

## Decision

| Concern | Choice |
|---|---|
| API framework | **FastAPI** on Python 3.12 |
| Database | **PostgreSQL 16 + pgvector** |
| ORM & migrations | **SQLAlchemy 2.0 + Alembic** |
| Background jobs | **Celery + Redis** |
| Graph engine | **NetworkX**, in-process |
| Auth | **JWT** access + refresh tokens, **Argon2** hashing |
| Frontend | **Next.js (App Router) + Tailwind CSS** |
| Local environment | **Docker Compose** |
| CI/CD | **GitHub Actions** |
| Hosting | **Render** (API + worker), **Neon** (Postgres), **Vercel** (frontend) |
| Testing | **pytest** + FastAPI `TestClient` |
| Observability | **structlog**, **Sentry**, `/health` |

## Alternatives considered

### API framework — why FastAPI over Django REST Framework or Flask

- **Django + DRF** — genuinely excellent for CRUD, and the admin is free. Rejected because its async
  support is bolted on rather than native, which matters when the API is I/O-bound, and because DRF
  serialisers are more ceremony than Pydantic for the same result. The ORM is also harder to fit into
  a clean repository layer, since Django models actively encourage `Model.objects` calls everywhere.
- **Flask** — minimal and flexible, but request validation and OpenAPI generation become third-party
  add-ons that must be wired together. FastAPI gives both from the same type annotations.

FastAPI wins because Pydantic validation, dependency injection, and auto-generated OpenAPI/Swagger
docs all fall out of ordinary type hints — and the OpenAPI docs are an explicit project requirement.

### Vectors — why pgvector over a dedicated vector database

`pgvector` is a PostgreSQL extension that adds a `vector` column type and similarity operators, so
embeddings live in the same table as everything else and are queried with ordinary SQL.

- **Pinecone / Weaviate / Qdrant** — faster at very large scale and richer in index options.
  Rejected because they create a **two-store consistency problem**: a job posting would exist in
  Postgres and its embedding in the vector DB, with no shared transaction. Deleting a job now means
  two writes that can partially fail. At this project's scale (thousands of vectors, not billions)
  the performance advantage is irrelevant and the operational cost is not.
- **FAISS in-process** — fast and free, but the index lives in memory, dies with the process, and
  cannot be shared between API replicas. That breaks the statelessness constraint.

`pgvector` keeps one database, one backup, one transaction boundary. `WHERE user_id = ... ORDER BY
embedding <=> $1` in a single query — a filtered vector search — is exactly the thing external vector
stores make awkward.

### Background jobs — why Celery over the alternatives

A **task queue** lets the API hand slow work to a separate pool of worker processes: the API writes a
message to a broker and returns immediately; a worker picks it up later. Think of a restaurant order
ticket — the waiter doesn't stand at the pass while your food cooks.

- **FastAPI `BackgroundTasks`** — runs after the response, but *inside the API process*. No retries,
  no persistence, no visibility, and it competes for the same CPU the API needs. A deploy mid-task
  loses the work silently. Fine for sending an email; wrong for a multi-second pipeline.
- **RQ (Redis Queue)** — simpler than Celery and genuinely appealing for a solo project. Rejected
  because Celery's retry policies, scheduled tasks, and result backend are things we actually want,
  and because Celery is what production Python shops overwhelmingly run — which matters for a
  portfolio project.
- **Dramatiq** — a good middle ground, but a smaller ecosystem and less interview recognition.

Redis serves as both broker and result backend, so it's one service rather than two.

### Graph engine — why NetworkX over Neo4j

- **Neo4j** — a real graph database with Cypher and persistent indexed traversal. Rejected because
  the skill graph is a few hundred nodes and a few thousand edges. That fits comfortably in memory
  and loads in milliseconds. Adding Neo4j means a third datastore to run locally, host on a free
  tier, back up, and keep in sync with the skills table in Postgres.
- **Hand-rolled adjacency lists + my own Dijkstra.** Tempting given the graph-theory coursework, and
  it would demonstrate the algorithm knowledge directly. Rejected as the default because
  battle-tested implementations of topological sort and shortest path are not where a portfolio
  project should spend its risk budget. *However*: the pathfinding logic in Phase 3 is where the
  graph theory is visible, so the custom weighting and ordering rules will be written explicitly
  rather than delegated wholesale.

The graph lives in Postgres as `skills` + `skill_edges` (the source of truth) and is loaded into a
NetworkX `DiGraph` in memory for traversal. Persistence and computation are cleanly separated.

### Auth — why JWT with refresh-token rotation

A **JWT** is a signed, self-describing token: it carries the user's identity in its payload, and the
server verifies the signature rather than looking anything up. Like a tamper-evident wristband — the
bouncer checks the seal, not a guest list.

The trade-off is that a JWT **cannot be revoked** before it expires. The standard answer, and the one
we take: **short-lived access tokens** (~15 min) paired with a **long-lived refresh token** that is
stored server-side, single-use, and **rotated** on every use — each refresh issues a new refresh
token and invalidates the old one. If a stolen refresh token is used, the legitimate one breaks, and
the theft is detectable.

- **Server-side sessions** — trivially revocable, but require shared session storage across replicas,
  which reintroduces the state we're trying to avoid.
- **Long-lived access tokens, no refresh** — simple and badly insecure; a leaked token is valid for
  its full lifetime with no remedy.

**Argon2** over bcrypt for hashing: it's the Password Hashing Competition winner and is memory-hard,
making GPU-based cracking substantially more expensive. bcrypt remains acceptable; Argon2 is the
current recommendation.

### Hosting — why Render + Neon + Vercel over a VPS

- **Self-managed VPS** (DigitalOcean/Hetzner droplet + nginx + systemd) — cheaper at scale, teaches
  more Linux, and gives full control. Rejected because it means no free tier, plus manual TLS
  renewal, OS patching, and building a deploy pipeline by hand. That work is real but it isn't the
  work this project is meant to demonstrate.
- **AWS (ECS/RDS/ALB)** — the most industry-relevant, but the free tier expires, the failure modes
  are expensive, and the setup effort would dominate the project.
- **Fly.io / Railway** — comparable to Render. Render was chosen for its native **background worker**
  service type, which maps exactly to the Celery worker and avoids hacks.

**Neon** rather than Render's own Postgres: Neon's free tier is not time-limited and supports
`pgvector`. **Vercel** for the frontend because Next.js is its first-class target and preview
deployments per pull request are free.

## Consequences

**Better**

- One database for relational data *and* vectors — no cross-store consistency problem.
- API and worker share one Docker image, so what runs is provably the same code.
- Stateless API scales horizontally without sticky sessions.
- Every choice is mainstream: recognisable in interviews and well-documented when things break.

**Worse / accepted**

- `pgvector` will be slower than a dedicated vector store past ~1M vectors. Acceptable; we're three
  orders of magnitude away and the migration path is a well-trodden one.
- Celery is heavier than the job actually requires, and its configuration surface is large. Accepted
  for the retry semantics and the ecosystem.
- The NetworkX graph is rebuilt in each process rather than shared, so a graph update needs a cache
  invalidation strategy. Deferred to Phase 3.
- Free-tier services cold-start. The deployed demo may take several seconds on first hit; this will
  be stated honestly in the README rather than hidden.
- Four separate hosting providers means four dashboards and four sets of environment variables to
  keep in sync.
