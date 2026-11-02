"""Layer 1 semantic router — in-memory KNN + optional Redis (M4B-06/07)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import numpy as np

from app.brain.embeddings import Embedder, knn_best
from app.kb.load import FaqEntry

logger = logging.getLogger("voice_agent.brain")


@dataclass(frozen=True)
class L1LookupResult:
    entry: FaqEntry | None
    similarity: float
    embed_ms: float
    knn_ms: float
    backend: str
    matched_question: str | None = None
    query_vec: np.ndarray | None = None


class InMemoryL1Router:
    """Embed question variants per intent; KNN at query time."""

    def __init__(
        self,
        entries: list[FaqEntry],
        embedder: Embedder,
    ) -> None:
        self._entries = entries
        self._embedder = embedder
        self._question_rows: list[tuple[int, str]] = []
        for entry_index, entry in enumerate(entries):
            for question in entry.embedded_questions:
                self._question_rows.append((entry_index, question))
        self._matrix = embedder.embed([question for _, question in self._question_rows])

    def lookup(self, query: str) -> L1LookupResult:
        t0 = time.perf_counter()
        query_vec = self._embedder.embed([query.strip()])[0]
        embed_ms = (time.perf_counter() - t0) * 1000.0

        t1 = time.perf_counter()
        idx, sim = knn_best(query_vec, self._matrix)
        knn_ms = (time.perf_counter() - t1) * 1000.0
        entry_index, matched_question = self._question_rows[idx]

        return L1LookupResult(
            entry=self._entries[entry_index],
            similarity=sim,
            embed_ms=embed_ms,
            knn_ms=knn_ms,
            backend="memory",
            matched_question=matched_question,
            query_vec=query_vec,
        )


def try_build_redis_l1_router(
    *,
    entries: list[FaqEntry],
    embedder: Embedder,
    redis_url: str,
    index_name: str,
) -> InMemoryL1Router | None:
    """Return Redis-backed router when redis stack is available; else None."""
    try:
        from app.brain.redis_index import RedisL1Router

        return RedisL1Router(
            entries=entries,
            embedder=embedder,
            redis_url=redis_url,
            index_name=index_name,
        )
    except Exception as exc:
        logger.warning("Redis L1 unavailable (%s); using in-memory router", exc)
        return None
