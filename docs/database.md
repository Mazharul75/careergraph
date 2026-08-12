# Database design

PostgreSQL 16 with the `pgvector` extension. One store for relational data and embeddings — see
[ADR-0002](adr/0002-technology-stack-selection.md) for why.

---

## Target ERD

The full intended schema. Tables marked ⬜ are designed but not yet migrated; they arrive with
the feature that needs them, so every migration ships alongside working code rather than as one
speculative up-front dump.

```mermaid
erDiagram
    USERS ||--o{ REFRESH_TOKENS : "issues"
    USERS ||--o{ RESUMES : "uploads"
    USERS ||--o{ JOBS : "posts"
    USERS ||--o{ USER_SKILLS : "has"
    SKILLS ||--o{ USER_SKILLS : "referenced by"
    SKILLS ||--o{ JOB_SKILLS : "required by"
    JOBS ||--o{ JOB_SKILLS : "requires"
    SKILLS ||--o{ SKILL_EDGES : "prerequisite of"
    USERS ||--o{ MATCHES : "receives"
    JOBS ||--o{ MATCHES : "scored in"

    USERS {
        uuid id PK
        varchar email UK "lowercase, CHECK-enforced"
        varchar password_hash "argon2id"
        varchar full_name
        user_role role "job_seeker | recruiter"
        boolean is_active
        timestamptz created_at
        timestamptz updated_at
    }

    REFRESH_TOKENS {
        uuid id PK
        uuid user_id FK
        varchar token_hash UK "sha256, never the token"
        uuid family_id "rotation chain id"
        timestamptz expires_at
        timestamptz revoked_at "null while valid"
        uuid replaced_by_id FK "successor token"
    }

    RESUMES {
        uuid id PK
        uuid user_id FK
        varchar original_filename
        parse_status status "pending|processing|complete|failed"
        text extracted_text
        vector embedding "pgvector"
        timestamptz created_at
    }

    SKILLS {
        uuid id PK
        varchar canonical_name UK
        varchar category
        smallint difficulty "1-5, path weighting"
    }

    SKILL_EDGES {
        uuid prerequisite_id FK
        uuid skill_id FK
        smallint weight "estimated learning effort"
    }

    USER_SKILLS {
        uuid user_id FK
        uuid skill_id FK
        smallint proficiency
        boolean confirmed "user corrected NLP output"
    }

    JOBS {
        uuid id PK
        uuid posted_by FK
        varchar title
        text description
        vector embedding "pgvector"
    }

    JOB_SKILLS {
        uuid job_id FK
        uuid skill_id FK
        smallint importance
    }

    MATCHES {
        uuid id PK
        uuid user_id FK
        uuid job_id FK
        real score
        jsonb breakdown "matched vs missing"
    }
```

| Table | Phase | Status |
|---|---|---|
| `users` | 1a | ✅ migrated |
| `refresh_tokens` | 1b | ✅ migrated |
| `resumes`, `skills`, `user_skills`, `jobs`, `job_skills`, `matches` | 2 | ⬜ |
| `skill_edges` | 3 | ⬜ |

## Normalization

The schema is in **third normal form**. The join tables are where that shows:

- A skill name is stored once, in `skills`. `user_skills` and `job_skills` reference it by ID.
  Storing skill names as text on each user would make "Postgres" and "PostgreSQL" separate
  skills and make renaming one an update across every row that mentions it.
- `skill_edges` is a pure many-to-many between skills, which is exactly what an edge list is.
  This table *is* the graph — NetworkX loads from it, it is not a second copy.
- `matches` is a deliberate, documented exception: `score` is derived data that could be
  recomputed from the two embeddings. It is cached because recomputation is expensive and the
  inputs are immutable once a resume is parsed.

## Conventions

**UUID primary keys, not serial integers.** Sequential IDs leak information — `/users/3` says
the system has almost no users, and `/users/4` is a guessable neighbour. UUIDs also let a
client generate an ID before the row exists.

**`timestamptz`, never naive timestamps.** Set by the database via `server_default=now()` and
`onupdate`, so values are correct even for rows written by a migration or by hand, and immune
to clock skew between application replicas.

**Explicit constraint naming.** `Base.metadata` carries a naming convention
(`app/db/base.py`). Without it PostgreSQL invents constraint names that differ between
databases, and Alembic ends up able to create a constraint it cannot later drop by name.

**Constraints in the database, not only in Python.** The `users.email` uniqueness and the
`email = lower(email)` CHECK are enforced by Postgres. An application-level check alone loses
to two concurrent registrations — both read "not taken", both insert.

**Soft deactivation over deletion.** `users.is_active` rather than `DELETE`. Hard-deleting a
user would cascade away their resumes and match history, unrecoverably.

## Migrations

Alembic, applied with `alembic upgrade head`. CI runs `upgrade head` → `downgrade base` →
`upgrade head` on every push, so a migration that cannot be reversed fails in review rather
than during an incident.

The `vector` extension is created by the **first migration**, not by a docker-compose init
script. Anything configured only in compose is a step someone must remember to repeat on Neon.

```bash
uv run alembic revision --autogenerate -m "add refresh tokens"
```

Always read generated migrations before committing. Autogenerate does not detect table or
column *renames* — it emits a drop plus an add, which silently destroys data.
