# Demo script — five minutes, start to finish

The narrative arc: **upload a resume → watch a background worker parse it → see extracted
skills → match against a job → get an *ordered* learning path.** Everything else exists in
service of that one flow.

## Before the demo (do this once, not in front of anyone)

1. Start Docker Desktop from the desktop shortcut and wait for it to settle.
2. From `D:\PProject`:

   ```
   docker compose up -d
   ```

3. From `D:\PProject\frontend`:

   ```
   npm run dev
   ```

4. Sanity check — both must succeed before you begin:
   - http://localhost:8000/health/ready → `{"status":"ready", ...}`
   - http://localhost:3000 → landing page renders.
5. Have a real one-page PDF resume on the desktop. A resume that mentions Python, SQL, and
   Docker demos far better than a lorem-ipsum file, because the extracted skills will look
   *plausible* instead of random.

## The flow (say the bold parts, roughly)

### 1. Register + login (30s)

Register a fresh account in the UI.

> **"Passwords are bcrypt-hashed, and the session is a 15-minute JWT plus a rotating refresh
> token — if a refresh token is ever stolen and replayed, the server detects the reuse and
> kills the whole session family."**

### 2. Upload the resume (60s)

Upload the PDF from the dashboard. Point at the status chip while it flips
`pending → processing → complete`.

> **"The upload returns HTTP 202 immediately — parsing happens in a Celery worker, a separate
> process, through a Redis queue. The UI is just polling the status column. If the worker is
> down, uploads still succeed and the queue drains when it comes back."**

If the interviewer wants proof, show the worker container's structured logs:

```
docker logs careergraph-worker-1 --tail 20
```

### 3. Review extracted skills (45s)

Open the skills page: extracted skills arrive as *suggestions* to confirm or reject.

> **"Extraction is deliberately human-in-the-loop. A resume saying 'familiar with Java' should
> not silently become a claim of Java proficiency — the user confirms each suggestion, and a
> rejected suggestion never comes back, even after re-upload."**

### 4. Add a job and see the match (60s)

Paste a real job description (keep one in a text file ready). Show the match score.

> **"The score blends two signals: skill overlap against a curated vocabulary, and cosine
> similarity between sentence embeddings stored in Postgres via pgvector — so 'built REST
> services in Python' matches 'FastAPI experience' with zero shared keywords."**

### 5. The learning path — the differentiator (90s)

Open the gap analysis for that job.

> **"Everything before this, keyword tools also do. The difference: skills live in a directed
> acyclic graph where an edge means 'prerequisite of'. Missing skills are topologically sorted,
> so you get *learn Linux basics, then Docker, then Kubernetes* — an ordered plan, not an
> unordered pile of gaps."**

### 6. If asked "is this production-ready?" (30s)

> **"CI runs lint, type-checks, and 356 tests on every push; deploys only trigger after CI
> passes, and the pipeline polls the health endpoint after deploying so a boot crash fails the
> pipeline instead of silently serving errors. Auth endpoints are rate-limited, logs are
> structured JSON with per-request correlation IDs, and background sweepers repair the two
> failure modes the happy path can't: expired token buildup and resumes orphaned between
> commit and enqueue."**

## Recovery lines (when something breaks live)

| Symptom | Say | Do |
|---|---|---|
| Parse stuck in `pending` | "This is exactly what the maintenance sweeper exists for — it re-enqueues anything stuck more than 15 minutes." | `docker compose restart worker` |
| API 500s | "Structured logs make this findable — every response carries an X-Request-ID that appears in every log line of that request." | `docker logs careergraph-api-1 --tail 50` |
| Frontend dead, API fine | Demo from Swagger instead. | http://localhost:8000/docs |
