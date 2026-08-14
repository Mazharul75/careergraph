# ADR-0009: fastembed (ONNX) for embeddings, with per-task worker recycling

- **Status:** Accepted
- **Date:** 2026-08-14
- **Phase:** 2c

## Context

Semantic matching needs an embedding model. The constraint that decides everything is memory:
the free Render web service has **512 MB**, shared by the API *and* the colocated Celery worker
([ADR-0008](0008-colocated-celery-worker.md)).

I measured the candidate before committing to it, rather than trusting a README:

```
baseline                :    21.0 MB
after `import fastembed`:    86.8 MB   (+66 MB for the import alone)
after model load        :   215.3 MB   (+128 MB, 0.4s once cached on disk)
after embedding 8 docs  :   221.4 MB   (0.05s)
PEAK OVER BASELINE      :   200.4 MB     384 dimensions
```

200 MB. With the API at roughly 150 MB, a worker holding the model puts the container near
500 MB of a 512 MB ceiling — before Argon2's 64 MB-per-login spike. Naively adopted, this OOMs.

## Decision

**Use fastembed with `BAAI/bge-small-en-v1.5`** (384 dimensions, quantised ONNX).

Three design constraints follow from the measurement, and they are the substance of this ADR:

1. **Never import fastembed at module scope.** `app/services/embedding.py` imports it *inside*
   `get_model()`. The API imports that module transitively and must not pay even the 66 MB
   import cost, let alone the model.
2. **Recycle the worker child after every task** (`worker_max_tasks_per_child=1`). This is what
   actually returns the 200 MB to the OS: CPython does not reliably hand freed arenas back, and
   ONNX Runtime allocates natively. The cost is a ~0.4s model load per task, which is nothing
   for a background job.
3. **Bake the model into the Docker image at build time.** Render's disk is ephemeral, so a
   runtime download repeats after every deploy and every cold start — 130 MB on the critical
   path of a user's first request. Verified: `/app/.model-cache` is 65 MB in the built image.

Embeddings are **best-effort**. A resume that parses and extracts skills but fails to embed
still completes; the match score falls back to skill coverage alone and the API reports
`semantic_available: false` so the client can explain a score that will change.

## Alternatives considered

- **sentence-transformers (PyTorch).** The default choice in every tutorial, and what most
  people would expect. Rejected on measurement: PyTorch alone is ~2 GB installed and hundreds
  of MB resident. It does not fit, and no amount of tuning makes it fit in 512 MB alongside an
  API and a worker.
- **A hosted embedding API** (OpenAI, Voyage, Cohere). Near-zero memory, better vectors, and it
  would make this entire ADR unnecessary. Rejected because it needs a card on file, adds a
  network failure mode to every parse, makes tests either mocked or metered, and weakens the
  project's story — "I called an API" is a thinner claim than a pipeline that runs locally.
- **A smaller model** (e.g. `all-MiniLM-L6-v2`). Comparable footprint, slightly weaker
  retrieval quality. bge-small is the better model at the same size.
- **Larger bge variants** (base, large). Better quality, several times the memory. Not viable.
- **Skipping embeddings and shipping skill matching only.** Genuinely tempting — skill coverage
  is the actionable signal, and it is the one users can act on. Rejected because "semantic
  matching, not keyword matching" is the product's central claim (PRD §G2, §S3), and dropping
  it would make the claim false.

## Consequences

**Better**

- Fits in the free tier, measured rather than hoped.
- Fully local: no API key, no per-request cost, tests run offline, the demo cannot break
  because someone's billing lapsed.
- The container starts ready — no first-request download.
- Scoring degrades gracefully instead of failing when a vector is missing.

**Worse / accepted**

- **Free-tier headroom is genuinely marginal.** Recycling bounds the exposure, but a parse and
  a burst of logins can still coincide. If the deployed demo starts getting OOM-killed, this is
  the cause, and the $7/month Render worker from ADR-0008 is the fix — it separates the 200 MB
  into its own instance and makes the problem disappear.
- ~0.4s model load per task, from recycling after every job.
- ~65 MB added to the image, and a slower Docker build.
- **Changing the embedding model is a migration, not a config change.** Vectors from different
  models are not comparable, so every stored embedding would need recomputing. The dimension is
  pinned in the schema to make that explicit rather than silently broken.
- Quantised ONNX weights differ marginally from the original float32 model, so scores are not
  bit-identical to a PyTorch baseline. Irrelevant for ranking; worth knowing if ever compared.
