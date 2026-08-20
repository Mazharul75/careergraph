"""Text embeddings.

An **embedding** turns a piece of text into a fixed-length vector of numbers positioned so that
texts with similar *meaning* land near each other. That is what lets "built REST services in
Python" match "experience with FastAPI" despite sharing no words — the thing keyword matching
fundamentally cannot do.

Similarity is measured by **cosine similarity**: the cosine of the angle between two vectors,
which ignores magnitude and compares direction only. Two documents saying the same thing at
different lengths still point the same way. Range is -1 to 1; for these normalised embeddings,
in practice 0 to 1.

## Why this module is shaped the way it is

The model costs **~200 MB of RSS** (measured, not estimated: 21 MB baseline → 221 MB after
loading and embedding). The free hosting instance has 512 MB shared with the API and the
colocated worker (ADR-0008). So:

* The model is **never loaded at import time**. Importing this module is free; the cost is paid
  on first use, inside the worker, and never in the API process at all.
* The worker recycles its child process frequently, which is what returns that 200 MB to the OS
  between jobs. See ADR-0009.
* The model files are baked into the Docker image at build time rather than downloaded on first
  use, because the free instance has an ephemeral disk — a runtime download would repeat after
  every deploy and every cold start.
* Loading is pinned to a **single ONNX thread** and the process runs with a capped glibc arena
  count (see the Dockerfile). Both are memory measures: the default thread pool is sized from
  the host's core count, not the container's memory limit, so an unconstrained load on a small
  instance allocates far more than the model itself needs.

**If this still gets OOM-killed**, set ``EMBEDDING_ENABLED=false``. Scoring falls back to skill
coverage alone, which is the component users can act on anyway — the semantic half is a
corroborator, not the verdict.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - import only for type checking
    from fastembed import TextEmbedding

logger = logging.getLogger(__name__)

# BAAI/bge-small-en-v1.5, served by fastembed as a quantised ONNX build. 384 dimensions,
# 33M parameters. Chosen for footprint: the larger bge models are better but do not fit.
MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSIONS = 384

_model: TextEmbedding | None = None
_lock = threading.Lock()


def get_model() -> TextEmbedding:
    """Return the process-wide model, loading it on first call.

    Double-checked locking because Celery's prefork pool can run threads within a child, and
    loading the model twice would briefly double a 200 MB allocation on a 512 MB box.
    """
    global _model
    if _model is None:
        with _lock:
            if _model is None:
                # Imported here, not at module scope: `import fastembed` alone costs ~66 MB,
                # and the API process imports this module transitively without ever embedding.
                from fastembed import TextEmbedding

                logger.info("Loading embedding model %s", MODEL_NAME)
                # threads=1 is a memory decision, not a speed one. ONNX Runtime allocates a
                # separate arena per intra-op thread, and on a multi-core host it sizes that
                # pool from the *host* core count -- which on a 512 MB instance is how a
                # ~200 MB model turns into an out-of-memory kill. One thread, one arena.
                # Embedding a single short document is not compute-bound anyway; the load is.
                _model = TextEmbedding(
                    model_name=MODEL_NAME,
                    threads=1,
                    providers=["CPUExecutionProvider"],
                )
                logger.info("Embedding model ready")
    return _model


def unload_model() -> None:
    """Drop the reference so the allocation can be reclaimed.

    Useful in tests. In the worker, process recycling is what actually returns memory to the
    OS — CPython does not reliably hand freed arenas back, and ONNX Runtime allocates natively.
    """
    global _model
    with _lock:
        _model = None


class EmbeddingDisabledError(RuntimeError):
    """Raised when embedding is switched off by configuration.

    A distinct type so callers can tell "deliberately disabled" apart from "the model failed
    to load", and log the second one loudly while treating the first as expected.
    """


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of documents.

    Batching matters: ONNX Runtime processes a batch in one pass, so eight documents cost far
    less than eight separate calls.
    """
    if not texts:
        return []

    from app.core.config import get_settings

    if not get_settings().embedding_enabled:
        raise EmbeddingDisabledError("Embedding is disabled by configuration.")

    return [vector.tolist() for vector in get_model().embed(texts)]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors, in pure Python.

    Postgres does this in SQL via pgvector's `<=>` operator for ranked search — that is the
    fast path and the one used for "find the best matches". This function exists for scoring a
    *single known pair*, where a round-trip to the database would cost more than the arithmetic,
    and for unit tests that must not require a database.
    """
    if len(a) != len(b):
        raise ValueError(f"Vector dimensions differ: {len(a)} vs {len(b)}")

    dot: float = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a: float = sum(x * x for x in a) ** 0.5
    norm_b: float = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        # A zero vector has no direction, so "similarity" is undefined rather than zero.
        # Returning 0.0 is the honest answer: no evidence of similarity.
        return 0.0
    return dot / (norm_a * norm_b)
