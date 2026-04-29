"""Embedding service.

Loads a sentence-transformers model lazily and exposes:
  - `EmbeddingService.encode(text)` → np.ndarray (float32, shape (384,))
  - `embed_resume_cached(db, path, service)` → cached resume vector keyed by
    (path, mtime, model).

Tests inject a `_model` to avoid downloading the real ~90 MB model.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import numpy as np

from shortlist.store.db import connect

DEFAULT_MODEL = "BAAI/bge-small-en-v1.5"


def _load_model(name: str = DEFAULT_MODEL, *, device: str | None = None) -> Any:
    from sentence_transformers import SentenceTransformer

    # Default to CPU. The embedding workload is tiny (a few hundred ~512-token
    # docs) and a CPU run takes seconds, so the GPU win is marginal at best.
    # Forcing CPU also sidesteps CUDA / compute-capability mismatches when the
    # installed torch was built for a newer GPU than the user has.
    # Override via SHORTLIST_EMBED_DEVICE env var (e.g. "cuda", "mps").
    chosen = device or os.environ.get("SHORTLIST_EMBED_DEVICE", "cpu")
    return SentenceTransformer(name, device=chosen)


class EmbeddingService:
    def __init__(self, *, model_name: str = DEFAULT_MODEL, _model: Any | None = None):
        self.model_name = model_name
        self._model = _model

    @property
    def model(self) -> Any:
        if self._model is None:
            self._model = _load_model(self.model_name)
        return self._model

    def encode(self, text: str) -> np.ndarray:
        out = self.model.encode(text, normalize_embeddings=True)
        if isinstance(out, np.ndarray) and out.ndim == 2:
            out = out[0]
        return np.asarray(out, dtype=np.float32)


def embed_resume_cached(
    db_path: Path, resume_path: Path, *, service: EmbeddingService
) -> np.ndarray:
    """Embed `resume_path`, caching by (path, mtime, model)."""
    resume_path = resume_path.expanduser().resolve()
    mtime = os.path.getmtime(resume_path)
    model = service.model_name

    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT vector FROM resume_embeddings WHERE path = ? AND mtime = ? AND model = ?",
            (str(resume_path), mtime, model),
        ).fetchone()
        if row is not None:
            return np.frombuffer(row[0], dtype=np.float32).copy()

        text = resume_path.read_text()
        vec = service.encode(text)
        conn.execute(
            "INSERT OR REPLACE INTO resume_embeddings (path, mtime, model, vector) "
            "VALUES (?, ?, ?, ?)",
            (str(resume_path), mtime, model, vec.tobytes()),
        )
        return vec
