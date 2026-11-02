"""Redis Stack vector index for L1 (M4B-04/05/06)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import numpy as np

from app.brain.l1 import L1LookupResult
from app.kb.load import FaqEntry

if TYPE_CHECKING:
    from app.brain.embeddings import Embedder


class RedisL1Router:
    """Redis Stack RediSearch vector index + KNN lookup."""

    def __init__(
        self,
        *,
        entries: list[FaqEntry],
        embedder: Embedder,
        redis_url: str,
        index_name: str = "brain:faq",
    ) -> None:
        import redis

        self._entries = entries
        self._entry_by_id = {entry.id: entry for entry in entries}
        self._embedder = embedder
        self._redis = redis.from_url(redis_url, decode_responses=False)
        self._index_name = index_name
        self._doc_prefix = f"{self._index_name}:doc:"
        self._question_rows: list[tuple[int, str]] = []
        for entry_index, entry in enumerate(entries):
            for question in entry.embedded_questions:
                self._question_rows.append((entry_index, question))
        self._matrix = embedder.embed([question for _, question in self._question_rows])
        self._check_redis_stack_modules()
        self._ensure_index()
        self._ensure_documents()

    @property
    def indexed_rows(self) -> int:
        return len(self._question_rows)

    def _check_redis_stack_modules(self) -> None:
        modules = self._redis.execute_command("MODULE", "LIST")
        names: set[str] = set()
        for module in modules:
            if not isinstance(module, list):
                continue
            for i in range(len(module) - 1):
                key = module[i]
                value = module[i + 1]
                key_text = key.decode() if isinstance(key, bytes) else str(key)
                if key_text == "name":
                    value_text = value.decode() if isinstance(value, bytes) else str(value)
                    names.add(value_text.lower())
                    break
        if "search" not in names and "ft" not in names:
            raise RuntimeError(
                "RediSearch module not found. Use redis-stack-server and verify MODULE LIST includes search."
            )

    def _ensure_index(self) -> None:
        import redis

        try:
            self._redis.execute_command("FT.INFO", self._index_name)
            return
        except redis.ResponseError as exc:
            if "Unknown Index name" not in str(exc):
                raise

        self._redis.execute_command(
            "FT.CREATE",
            self._index_name,
            "ON",
            "HASH",
            "PREFIX",
            1,
            self._doc_prefix,
            "SCHEMA",
            "faq_id",
            "TAG",
            "question",
            "TEXT",
            "answer",
            "TEXT",
            "category",
            "TAG",
            "tags",
            "TAG",
            "vector",
            "VECTOR",
            "HNSW",
            6,
            "TYPE",
            "FLOAT32",
            "DIM",
            self._embedder.dimension,
            "DISTANCE_METRIC",
            "COSINE",
        )

    def _ensure_documents(self) -> None:
        # Keys are positional, so every row is rewritten to stay in sync with faqs.yaml.
        written: set[bytes] = set()
        for row_index, row in enumerate(self._matrix):
            entry_index, question = self._question_rows[row_index]
            entry = self._entries[entry_index]
            key = f"{self._doc_prefix}{row_index}".encode()
            written.add(key)
            vector_blob = np.asarray(row, dtype=np.float32).tobytes()
            tags = ",".join(entry.tags)
            self._redis.hset(
                key,
                mapping={
                    b"faq_id": entry.id.encode(),
                    b"question": question.encode(),
                    b"answer": entry.answer.encode(),
                    b"category": entry.category.encode(),
                    b"tags": tags.encode(),
                    b"vector": vector_blob,
                },
            )
        for key in list(self._redis.scan_iter(match=f"{self._doc_prefix}*")):
            if key not in written:
                self._redis.delete(key)

    def lookup(self, query: str) -> L1LookupResult:
        t0 = time.perf_counter()
        query_vec = self._embedder.embed([query.strip()])[0]
        embed_ms = (time.perf_counter() - t0) * 1000.0

        t1 = time.perf_counter()
        query_blob = np.asarray(query_vec, dtype=np.float32).tobytes()
        result = self._redis.execute_command(
            "FT.SEARCH",
            self._index_name,
            "*=>[KNN 1 @vector $query_vec AS distance]",
            "PARAMS",
            2,
            "query_vec",
            query_blob,
            "SORTBY",
            "distance",
            "ASC",
            "RETURN",
            3,
            "faq_id",
            "question",
            "distance",
            "DIALECT",
            2,
        )
        knn_ms = (time.perf_counter() - t1) * 1000.0
        if not result or int(result[0]) == 0:
            return L1LookupResult(
                entry=None,
                similarity=0.0,
                embed_ms=embed_ms,
                knn_ms=knn_ms,
                backend="redis",
                matched_question=None,
                query_vec=query_vec,
            )

        fields = _to_field_map(result[2])
        faq_id = _to_text(fields.get("faq_id", b""))
        matched_question = _to_text(fields.get("question", b"")) or None
        distance = float(_to_text(fields.get("distance", b"1.0")) or "1.0")
        similarity = max(0.0, min(1.0, 1.0 - distance))
        entry = self._entry_by_id.get(faq_id)

        return L1LookupResult(
            entry=entry,
            similarity=similarity,
            embed_ms=embed_ms,
            knn_ms=knn_ms,
            backend="redis",
            matched_question=matched_question,
            query_vec=query_vec,
        )


def _to_field_map(payload: list[Any]) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for i in range(0, len(payload), 2):
        key_raw = payload[i]
        if i + 1 >= len(payload):
            continue
        value = payload[i + 1]
        key = key_raw.decode() if isinstance(key_raw, bytes) else str(key_raw)
        if isinstance(value, bytes):
            out[key] = value
        else:
            out[key] = str(value).encode()
    return out


def _to_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode()
    return str(value)
