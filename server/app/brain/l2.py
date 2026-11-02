"""Layer 2 retrieval (M4B-09/10): FAQ chunks from Qdrant, with an in-memory fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

import numpy as np

from app.brain.embeddings import Embedder, knn_top
from app.kb.load import FaqEntry

logger = logging.getLogger("voice_agent.brain")


@dataclass(frozen=True)
class L2Chunk:
    faq_id: str
    question: str
    answer: str
    score: float


class L2Retriever(Protocol):
    backend: str

    def search(self, query_vec: np.ndarray, k: int) -> list[L2Chunk]: ...


def chunk_text(entry: FaqEntry) -> str:
    """One chunk per intent: all question variants plus the answer."""
    return " ".join(entry.embedded_questions) + "\n" + entry.answer


class InMemoryL2Retriever:
    backend = "memory"

    def __init__(self, entries: list[FaqEntry], embedder: Embedder) -> None:
        self._entries = entries
        self._matrix = embedder.embed([chunk_text(e) for e in entries])

    def search(self, query_vec: np.ndarray, k: int) -> list[L2Chunk]:
        return [
            L2Chunk(
                faq_id=self._entries[i].id,
                question=self._entries[i].question,
                answer=self._entries[i].answer,
                score=score,
            )
            for i, score in knn_top(query_vec, self._matrix, k)
        ]


def build_l2_retriever(
    *,
    entries: list[FaqEntry],
    embedder: Embedder,
    qdrant_url: str | None,
    collection: str,
) -> L2Retriever:
    """Qdrant when QDRANT_URL is set and reachable; otherwise in-memory (same API)."""
    if qdrant_url:
        try:
            from qdrant_client import QdrantClient

            from app.brain.qdrant_store import QdrantL2Retriever

            return QdrantL2Retriever(
                entries=entries,
                embedder=embedder,
                client=QdrantClient(url=qdrant_url, timeout=2),
                collection=collection,
            )
        except Exception as exc:
            logger.warning("Qdrant L2 unavailable (%s); using in-memory retriever", exc)
    return InMemoryL2Retriever(entries, embedder)
