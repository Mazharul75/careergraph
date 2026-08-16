# ADR-0012: Embedding runs as its own task, after the parse commits

- **Status:** Accepted
- **Date:** 2026-08-16
- **Phase:** 7 (post-deployment fix)

## Context

The first resume uploaded to the live deployment never finished parsing. Diagnosis from the
production logs:

- `resumes.parse` was received at 13:37:43. Celery's `[tasks]` startup banner printed again at
  13:38:38 — that banner appears **only when a worker starts**, so the worker had restarted 55
  seconds into the job. No `succeeded` line was ever written.
- 55 s is well under the 120 s soft time limit, so this was not a timeout. It is almost exactly
  how long loading the ~200 MB embedding model takes on a cold free instance.
- The instance has 512 MB shared between the API (~150 MB) and the colocated worker (~100 MB),
  per ADR-0008. The model does not fit on top of that.

`parse_resume` already treated embedding as best effort — the call sat inside `try/except` with
a comment saying a resume with text and skills but no vector is still useful. **That protection
was fictional.** An out-of-memory kill terminates the process; no `except` clause runs. The
failure it was written to absorb was precisely the one it could not catch.

Two further defects turned a recoverable crash into a permanent hang:

- Redis has no native message acknowledgement, so `task_acks_late` is emulated with a
  **visibility timeout, default 3600 s**. The killed worker's message stayed invisible for an
  hour, which to a user is indistinguishable from the system having silently given up.
- `requeue_stuck_resumes` swept only `pending` rows, but `parse_resume` sets `processing` and
  commits before doing the heavy work. The sweeper built to repair exactly this failure did not
  look at the state the failure produces.

## Decision

**Split embedding into its own Celery task, `resumes.embed`, enqueued only after the parse
transaction has committed.**

`parse_resume` now extracts text, matches skills, marks the resume `complete`, drops the
uploaded bytes, and commits — all without importing the model. Only then does it enqueue
`resumes.embed`, which loads the model and writes the vector in a separate transaction.

The ordering is the entire point: the resume is durably useful *before* the process-fatal step
begins. An OOM kill during embedding now costs one vector, not the parse, and match scoring
falls back to skill overlap alone until the vector arrives.

Supporting changes:

- `broker_transport_options.visibility_timeout = 600`. Must remain above the 180 s hard time
  limit — set below it and a still-running task is handed to a second worker and executed twice.
- `requeue_stuck_resumes` now covers `processing` as well as `pending`.
- `--max-tasks-per-child` corrected to `1` in `Procfile` and `render.yaml`, matching `config.py`
  and the reasoning already recorded in ADR-0009. The CLI flag overrides the setting, so
  production had been holding the model resident across ten tasks while the config file claimed
  otherwise.

## Alternatives considered

- **Upgrade to Render Starter ($7/mo, 2 GB).** Would fix the symptom with no code change, and
  ADR-0008 already names it as the documented upgrade path. Rejected as the *primary* fix
  because the design defect is real independent of the plan: a task that loses committed work
  when its optional final step dies is wrong at any memory limit. The upgrade remains available
  and now buys throughput rather than correctness.
- **Disable embeddings on the free tier behind a flag.** Simple and reliable, but it deletes the
  semantic matching that distinguishes this project from keyword search — trading the
  differentiator for uptime.
- **Keep embedding inline and catch the failure properly.** Not possible. There is no way to
  catch SIGKILL from inside the process being killed. A memory guard checking free RAM before
  loading would be a guess about a moving target, and would still leave the resume stranded.
- **Retry the whole parse on a smaller code path.** Re-extracting text to reach the embedding
  step repeats work that already succeeded, and would re-run on every redelivery.

## Consequences

**Good.** Parse latency dropped from ~55 s (or death) to **1.29 s measured live**, because the
common path no longer touches the model at all. The pipeline now degrades along a sensible axis:
text and skills are guaranteed, the vector is best effort *in fact* rather than in a comment.
Two failure modes that were invisible are now covered by tests.

**Bad.** Match scores can show skill-overlap-only for a window after upload, and on a 512 MB
instance the embed task may fail repeatedly — the resume is fine, the semantic half may simply
not arrive until the instance is upgraded. The frontend already polls for the semantic half and
renders without it, so this degrades visibly rather than silently.

**Also.** Two Celery tasks now write to the same row at different times. Both are idempotent and
touch disjoint columns, so they cannot conflict, but any third writer must respect that.

## The lesson worth carrying

Wrapping a call in `try/except` does not make it best-effort. It makes it best-effort *for the
failures that leave your process alive*. When the failure mode is the process dying, the only
real protection is committing the valuable work before the dangerous work starts.
