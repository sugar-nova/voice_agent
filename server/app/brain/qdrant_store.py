"""Qdrant collection for L2 FAQ chunks (M4B-08/09)."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import numpy as np

from app.brain.embeddings import Embedder
from app.brain.l2 import L2Chunk, chunk_text
from app.kb.load import FaqEntry

if TYPE_CHECKING:
    from qdrant_client import QdrantClient


class QdrantL2Retriever:
    backend = "qdrant"

    def __init__(
        self,
        *,
        entries: list[FaqEntry],
        embedder: Embedder,
        client: QdrantClient,
        collection: str,
    ) -> None:
        from qdrant_client.http.models import (
            Distance,
            FieldCondition,
            Filter,
            FilterSelector,
            MatchAny,
            PointStruct,
            VectorParams,
        )

        self._client = client
        self._collection = collection
        if not client.collection_exists(collection):
            client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=embedder.dimension, distance=Distance.COSINE),
            )

        # Point ids derive from faq_id, so upserting keeps the collection in sync with faqs.yaml.
        vectors = embedder.embed([chunk_text(e) for e in entries])
        client.upsert(
            collection_name=collection,
            points=[
                PointStruct(
                    id=str(uuid.uuid5(uuid.NAMESPACE_URL, entry.id)),
                    vector=vector.tolist(),
                    payload={
                        "faq_id": entry.id,
                        "category": entry.category,
                        "tags": list(entry.tags),
                        "question": entry.question,
                        "answer": entry.answer,
                    },
                )
                for entry, vector in zip(entries, vectors, strict=True)
            ],
        )
        client.delete(
            collection_name=collection,
            points_selector=FilterSelector(
                filter=Filter(
                    must_not=[
                        FieldCondition(key="faq_id", match=MatchAny(any=[e.id for e in entries]))
                    ]
                )
            ),
        )

    @property
    def point_count(self) -> int:
        return self._client.count(collection_name=self._collection).count

    def search(self, query_vec: np.ndarray, k: int) -> list[L2Chunk]:
        hits = self._client.query_points(
            collection_name=self._collection,
            query=query_vec.tolist(),
            limit=k,
            with_payload=True,
        ).points
        return [
            L2Chunk(
                faq_id=str(hit.payload["faq_id"]),
                question=str(hit.payload["question"]),
                answer=str(hit.payload["answer"]),
                score=float(hit.score),
            )
            for hit in hits
            if hit.payload
        ]
