from __future__ import annotations

import sys
from types import SimpleNamespace

import numpy as np
import pytest

from app.brain.redis_index import RedisL1Router
from app.kb.load import FaqEntry


class StubEmbedder:
    @property
    def dimension(self) -> int:
        return 3

    def embed(self, texts: list[str]) -> np.ndarray:
        rows = []
        for text in texts:
            lowered = text.lower()
            if "where" in lowered:
                rows.append(np.array([1.0, 0.0, 0.0], dtype=np.float32))
            elif "receipt" in lowered:
                rows.append(np.array([0.0, 1.0, 0.0], dtype=np.float32))
            else:
                rows.append(np.array([0.0, 0.0, 1.0], dtype=np.float32))
        return np.vstack(rows)


class FakeResponseError(Exception):
    pass


class FakeRedisClient:
    def __init__(self) -> None:
        self.index_created = False
        self.docs: set[bytes] = set()
        self.search_result: list[object] = [
            1,
            b"brain:faq:doc:0",
            [
                b"faq_id",
                b"where_is_money",
                b"question",
                b"Where is my money?",
                b"distance",
                b"0.05",
            ],
        ]

    def hset(self, key: bytes, mapping: dict[bytes, bytes]) -> int:
        self.docs.add(key)
        return len(mapping)

    def scan_iter(self, match: str) -> list[bytes]:
        prefix = match.rstrip("*").encode()
        return [key for key in self.docs if key.startswith(prefix)]

    def delete(self, key: bytes) -> int:
        self.docs.discard(key)
        return 1

    def execute_command(self, *args: object) -> object:
        if args[0] == "MODULE" and args[1] == "LIST":
            return [[b"name", b"search", b"ver", 20999]]
        if args[0] == "FT.INFO":
            if not self.index_created:
                raise FakeResponseError("Unknown Index name")
            return [b"index_name", b"brain:faq"]
        if args[0] == "FT.CREATE":
            self.index_created = True
            return b"OK"
        if args[0] == "FT.SEARCH":
            return self.search_result
        raise AssertionError(f"Unexpected command: {args}")


def _fake_entries() -> list[FaqEntry]:
    return [
        FaqEntry(
            id="where_is_money",
            question="Where is my money?",
            embedded_questions=("Where is my money?", "Where can I track my transfer?"),
            answer="Open Activity to track your transfer.",
            category="tracking",
            tags=("tracking", "status"),
        )
    ]


def test_redis_router_creates_index_and_docs(monkeypatch) -> None:
    client = FakeRedisClient()
    fake_redis_module = SimpleNamespace(
        from_url=lambda *_args, **_kwargs: client,
        ResponseError=FakeResponseError,
    )
    monkeypatch.setitem(sys.modules, "redis", fake_redis_module)

    router = RedisL1Router(
        entries=_fake_entries(),
        embedder=StubEmbedder(),
        redis_url="redis://127.0.0.1:6379",
        index_name="brain:faq",
    )
    assert router.indexed_rows == 2
    assert client.index_created
    assert len(client.docs) == 2


def test_redis_router_removes_stale_docs(monkeypatch) -> None:
    client = FakeRedisClient()
    client.docs.add(b"brain:faq:doc:7")
    fake_redis_module = SimpleNamespace(
        from_url=lambda *_args, **_kwargs: client,
        ResponseError=FakeResponseError,
    )
    monkeypatch.setitem(sys.modules, "redis", fake_redis_module)

    RedisL1Router(
        entries=_fake_entries(),
        embedder=StubEmbedder(),
        redis_url="redis://127.0.0.1:6379",
        index_name="brain:faq",
    )
    assert client.docs == {b"brain:faq:doc:0", b"brain:faq:doc:1"}


def test_redis_router_lookup_reads_redis_knn(monkeypatch) -> None:
    client = FakeRedisClient()
    fake_redis_module = SimpleNamespace(
        from_url=lambda *_args, **_kwargs: client,
        ResponseError=FakeResponseError,
    )
    monkeypatch.setitem(sys.modules, "redis", fake_redis_module)

    router = RedisL1Router(
        entries=_fake_entries(),
        embedder=StubEmbedder(),
        redis_url="redis://127.0.0.1:6379",
        index_name="brain:faq",
    )
    result = router.lookup("Where is my money?")
    assert result.entry is not None
    assert result.entry.id == "where_is_money"
    assert result.backend == "redis"
    assert result.matched_question == "Where is my money?"
    assert result.similarity == pytest.approx(0.95)
