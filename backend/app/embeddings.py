"""Text embeddings for step merging, alignment and search.

Uses a small local sentence-transformers model by default. If the model cannot be
loaded (no internet on first run, or the package is missing), it falls back to a
deterministic hashing embedder so the app keeps working; the fallback is logged
and reported by ``/api/health``.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from app.config import get_settings

log = logging.getLogger("replay.embeddings")

FloatArray = npt.NDArray[np.float32]

_TOKEN = re.compile(r"[a-z0-9]+")


class Embedder(Protocol):
    name: str

    def embed(self, texts: list[str]) -> FloatArray: ...


def _normalize(mat: FloatArray) -> FloatArray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return (mat / norms).astype(np.float32)


class HashEmbedder:
    """Bag of words + character trigrams hashed into a fixed vector. Offline, fast."""

    name = "hash-512"

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    def _features(self, text: str) -> list[str]:
        from app.pipeline.textnorm import stem

        words = [stem(w) for w in _TOKEN.findall(text.lower())]
        feats = [f"w:{w}" for w in words]
        for w in words:
            padded = f"#{w}#"
            feats.extend(f"c:{padded[i : i + 3]}" for i in range(max(1, len(padded) - 2)))
        return feats

    def embed(self, texts: list[str]) -> FloatArray:
        mat = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for feat in self._features(text):
                digest = hashlib.blake2b(feat.encode(), digest_size=8).digest()
                idx = int.from_bytes(digest[:4], "little") % self.dim
                sign = 1.0 if digest[4] & 1 else -1.0
                weight = 1.0 if feat.startswith("w:") else 0.35
                mat[row, idx] += sign * weight
        return _normalize(mat)


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer

        self.name = model_name
        self._model: Any = SentenceTransformer(model_name, device="cpu")
        self._lock = threading.Lock()

    def embed(self, texts: list[str]) -> FloatArray:
        if not texts:
            return np.zeros((0, 384), dtype=np.float32)
        with self._lock:
            vecs = self._model.encode(
                texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False
            )
        return np.asarray(vecs, dtype=np.float32)


_embedder: Embedder | None = None
_embedder_lock = threading.Lock()
_status = "not loaded"


def get_embedder() -> Embedder:
    global _embedder, _status
    if _embedder is not None:
        return _embedder
    with _embedder_lock:
        if _embedder is not None:
            return _embedder
        s = get_settings()
        if s.embedding_backend == "hash":
            _embedder = HashEmbedder()
            _status = _embedder.name
            return _embedder
        try:
            _embedder = SentenceTransformerEmbedder(s.embedding_model)
            _status = f"sentence-transformers/{s.embedding_model}"
        except Exception as exc:
            if s.embedding_backend == "sentence-transformers":
                raise
            log.warning("Embedding model unavailable (%s); using hashing fallback", exc)
            _embedder = HashEmbedder()
            _status = f"{_embedder.name} (fallback)"
        log.info("Embeddings: %s", _status)
        return _embedder


def embedding_status() -> str:
    if _embedder is None:
        s = get_settings()
        return "hash-512" if s.embedding_backend == "hash" else f"{s.embedding_model} (lazy)"
    return _status


def reset_embedder() -> None:
    global _embedder, _status
    _embedder = None
    _status = "not loaded"


def cosine_matrix(a: FloatArray, b: FloatArray) -> FloatArray:
    if a.size == 0 or b.size == 0:
        return np.zeros((a.shape[0], b.shape[0]), dtype=np.float32)
    return (_normalize(a) @ _normalize(b).T).astype(np.float32)
