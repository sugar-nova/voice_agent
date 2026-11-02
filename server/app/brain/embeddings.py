"""Text embeddings for semantic router (M4B-03)."""

from __future__ import annotations

from typing import Protocol

import numpy as np


class Embedder(Protocol):
    @property
    def dimension(self) -> int: ...

    def embed(self, texts: list[str]) -> np.ndarray: ...


class FastEmbedder:
    """Local embeddings via fastembed (pinned model in Settings)."""

    def __init__(self, model_name: str) -> None:
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name=model_name)
        probe = list(self._model.embed(["probe"]))
        self._dimension = len(probe[0])

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> np.ndarray:
        rows = [np.asarray(vec, dtype=np.float32) for vec in self._model.embed(texts)]
        return np.vstack(rows)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def knn_best(query_vec: np.ndarray, matrix: np.ndarray) -> tuple[int, float]:
    """Return index and cosine similarity of best row in matrix."""
    return knn_top(query_vec, matrix, 1)[0]


def knn_top(query_vec: np.ndarray, matrix: np.ndarray, k: int) -> list[tuple[int, float]]:
    """Return up to k (index, cosine similarity) pairs, best first."""
    norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query_vec)
    dots = matrix @ query_vec
    with np.errstate(divide="ignore", invalid="ignore"):
        sims = np.where(norms > 0, dots / norms, 0.0)
    order = np.argsort(-sims)[:k]
    return [(int(i), float(sims[i])) for i in order]
