from __future__ import annotations

import numpy as np
import pytest

from app.kb.load import FaqEntry

qdrant_client = pytest.importorskip("qdrant_client")

from app.brain.qdrant_store import QdrantL2Retriever  # noqa: E402


class KeywordEmbedder:
    @property
    def dimension(self) -> int:
        return 3

    def embed(self, texts: list[str]) -> np.ndarray:
        rows = []
        for text in texts:
            lowered = text.lower()
            rows.append(
                np.array(
                    [
                        1.0 if "where" in lowered else 0.0,
                        1.0 if "receipt" in lowered else 0.0,
                        1.0 if "fail" in lowered else 0.0,
                    ],
                    dtype=np.float32,
                )
                + 0.01
            )
        return np.vstack(rows)


def _entry(faq_id: str, question: str, answer: str) -> FaqEntry:
    return FaqEntry(
        id=faq_id,
        question=question,
        embedded_questions=(question,),
        answer=answer,
        category="tracking",
        tags=("tracking",),
    )


ENTRIES = [
    _entry("where_is_money", "Where is my money?", "Open Activity."),
    _entry("proof_of_payment", "Can I get a receipt?", "Download the receipt."),
    _entry("transfer_failed", "My transfer failed", "Money is returned."),
]


def test_qdrant_retriever_returns_best_chunk_first() -> None:
    client = qdrant_client.QdrantClient(":memory:")
    embedder = KeywordEmbedder()
    retriever = QdrantL2Retriever(
        entries=ENTRIES, embedder=embedder, client=client, collection="faq"
    )

    chunks = retriever.search(embedder.embed(["I need a receipt"])[0], 2)
    assert retriever.point_count == 3
    assert [c.faq_id for c in chunks][0] == "proof_of_payment"
    assert chunks[0].answer == "Download the receipt."
    assert chunks[0].score >= chunks[1].score


def test_qdrant_retriever_removes_faqs_dropped_from_kb() -> None:
    client = qdrant_client.QdrantClient(":memory:")
    embedder = KeywordEmbedder()
    QdrantL2Retriever(entries=ENTRIES, embedder=embedder, client=client, collection="faq")

    retriever = QdrantL2Retriever(
        entries=ENTRIES[:2], embedder=embedder, client=client, collection="faq"
    )
    assert retriever.point_count == 2
