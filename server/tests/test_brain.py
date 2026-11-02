"""Brain routing tests (M4B-06/13) with deterministic mock embeddings."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Sequence

import numpy as np

from app.brain.decision import BrainService
from app.brain.l1 import InMemoryL1Router
from app.brain.l2 import InMemoryL2Retriever, L2Chunk
from app.brain.types import DEFLECT_HANDOFF_TEXT
from app.config import Settings
from app.kb.load import FaqEntry, load_faqs


class MockEmbedder:
    def __init__(self, entries: list[FaqEntry]) -> None:
        self._entries = entries
        self._rows: list[tuple[int, str]] = []
        for entry_index, entry in enumerate(entries):
            for question in entry.embedded_questions:
                self._rows.append((entry_index, question.lower().strip()))
        self._dimension = len(self._rows)

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed(self, texts: list[str]) -> np.ndarray:
        rows = []
        for text in texts:
            vec = np.zeros(self._dimension, dtype=np.float32)
            lowered = text.lower().strip()
            matched = False
            for index, (_, question) in enumerate(self._rows):
                if question == lowered or question in lowered or lowered in question:
                    vec[index] = 1.0
                    matched = True
            if not matched:
                # Deliberately non-matching vector for out-of-scope queries in tests.
                vec[-1] = 0.01
                vec[-2] = 0.01
            rows.append(vec)
        return np.vstack(rows)


def _brain_settings(**overrides: object) -> Settings:
    base = Settings.from_env()
    return Settings(
        env_file=base.env_file,
        deepgram_api_key=base.deepgram_api_key,
        cartesia_api_key=base.cartesia_api_key,
        cartesia_voice_id=base.cartesia_voice_id,
        port=base.port,
        log_level=base.log_level,
        agent_mode="brain",
        brain_l1_threshold=float(overrides.get("brain_l1_threshold", 0.95)),
        brain_enable_l2=bool(overrides.get("brain_enable_l2", True)),
        brain_l2_relevance_floor=float(overrides.get("brain_l2_relevance_floor", 0.5)),
        embedding_provider="mock",
        embedding_model="mock",
        redis_url=None,
        redis_index_name="brain:faq",
        qdrant_url=None,
        qdrant_collection="wise_where_is_money",
        ollama_url="http://127.0.0.1:11434",
        ollama_model="qwen2.5:3b",
    )


class FakeSynthesizer:
    def __init__(self, tokens: list[str], *, fail: bool = False) -> None:
        self._tokens = tokens
        self._fail = fail
        self.calls: list[tuple[str, list[str]]] = []

    async def stream(self, query: str, chunks: Sequence[L2Chunk]) -> AsyncGenerator[str, None]:
        self.calls.append((query, [chunk.faq_id for chunk in chunks]))
        if self._fail:
            raise ConnectionError("ollama down")
        for token in self._tokens:
            yield token


class FixedRetriever:
    backend = "fixed"

    def __init__(self, score: float) -> None:
        self._score = score

    def search(self, _query_vec: np.ndarray, k: int) -> list[L2Chunk]:
        chunk = L2Chunk(
            faq_id="still_processing",
            question="Why is my transfer still processing?",
            answer="It can be slower on weekends.",
            score=self._score,
        )
        return [chunk][:k]


def _l2_service(*, score: float, llm: FakeSynthesizer, floor: float = 0.6) -> BrainService:
    entries = load_faqs()
    return BrainService(
        settings=_brain_settings(brain_l2_relevance_floor=floor),
        l1=InMemoryL1Router(entries, MockEmbedder(entries)),
        l2=FixedRetriever(score),
        llm=llm,
    )


def test_faqs_yaml_loads() -> None:
    entries = load_faqs()
    assert len(entries) >= 8
    assert all(entry.answer for entry in entries)


def test_l1_returns_matching_faq_for_canonical_question() -> None:
    entries = load_faqs()
    embedder = MockEmbedder(entries)
    router = InMemoryL1Router(entries, embedder)
    result = router.lookup("Where is my money?")
    assert result.entry is not None
    assert result.entry.id == "where_is_money"
    assert result.similarity >= 0.99


def test_l1_returns_matching_faq_for_question_variant() -> None:
    entries = load_faqs()
    embedder = MockEmbedder(entries)
    router = InMemoryL1Router(entries, embedder)
    result = router.lookup("How can I see my transfer status?")
    assert result.entry is not None
    assert result.entry.id == "where_is_money"
    assert result.similarity >= 0.99


async def test_brain_routes_l1_hit_and_l1_only_deflect() -> None:
    entries = load_faqs()
    embedder = MockEmbedder(entries)
    l1 = InMemoryL1Router(entries, embedder)

    l1_hit = await BrainService(settings=_brain_settings(), l1=l1).decide("Where is my money?")
    assert l1_hit.route == "l1_hit"
    assert "Activity" in l1_hit.answer_text

    deflect = await BrainService(settings=_brain_settings(brain_enable_l2=False), l1=l1).decide(
        "What are your opening hours?"
    )
    assert deflect.route == "deflect"
    assert deflect.answer_text == DEFLECT_HANDOFF_TEXT


async def test_brain_l1_hit_does_not_call_l2() -> None:
    entries = load_faqs()
    embedder = MockEmbedder(entries)
    l1 = InMemoryL1Router(entries, embedder)

    class ExplodingL2:
        backend = "exploding"

        def search(self, _query_vec, _k):  # pragma: no cover - should never execute
            raise AssertionError("L2 should not be called on L1 hit")

    llm = FakeSynthesizer(["unused"])
    service = BrainService(
        settings=_brain_settings(brain_l1_threshold=0.95, brain_enable_l2=True),
        l1=l1,
        l2=ExplodingL2(),  # type: ignore[arg-type]
        llm=llm,
    )
    decision = await service.decide("Where is my money?")
    assert decision.route == "l1_hit"
    assert llm.calls == []


async def test_l2_streams_grounded_answer_when_llm_covers_it() -> None:
    llm = FakeSynthesizer(["Yes", ", it can", " be slower", " on weekends."])
    decision = await _l2_service(score=0.8, llm=llm).decide("Is it slower on weekends?")

    assert decision.route == "l2_rag"
    assert decision.faq_id == "still_processing"
    assert decision.answer_stream is not None
    rest = [token async for token in decision.answer_stream]
    assert decision.answer_text + "".join(rest) == "Yes, it can be slower on weekends."
    assert decision.metrics.qdrant_search_ms is not None
    assert decision.metrics.llm_first_token_ms is not None
    assert llm.calls == [("Is it slower on weekends?", ["still_processing"])]


async def test_l2_not_covered_deflects() -> None:
    llm = FakeSynthesizer(["NOT", "_CO", "VERED"])
    decision = await _l2_service(score=0.8, llm=llm).decide("What are your fees?")

    assert decision.route == "deflect"
    assert decision.answer_text == DEFLECT_HANDOFF_TEXT
    assert decision.answer_stream is None
    assert decision.metrics.llm_first_token_ms is not None


async def test_l2_below_relevance_floor_deflects_without_llm() -> None:
    llm = FakeSynthesizer(["unused"])
    decision = await _l2_service(score=0.4, llm=llm, floor=0.6).decide("Reset my password")

    assert decision.route == "deflect"
    assert decision.metrics.qdrant_search_ms is not None
    assert decision.metrics.llm_first_token_ms is None
    assert llm.calls == []


async def test_l2_llm_failure_deflects() -> None:
    decision = await _l2_service(score=0.8, llm=FakeSynthesizer([], fail=True)).decide(
        "Is it slower on weekends?"
    )
    assert decision.route == "deflect"


def test_in_memory_l2_retriever_returns_top_k_best_first() -> None:
    entries = load_faqs()
    embedder = MockEmbedder(entries)
    retriever = InMemoryL2Retriever(entries, embedder)
    query_vec = embedder.embed(["Can I get proof of payment for my transfer?"])[0]

    chunks = retriever.search(query_vec, 3)
    assert len(chunks) == 3
    assert chunks[0].faq_id == "proof_of_payment"
    assert chunks[0].score >= chunks[1].score >= chunks[2].score


async def test_l1_metrics_include_non_null_timings() -> None:
    entries = load_faqs()
    embedder = MockEmbedder(entries)
    l1 = InMemoryL1Router(entries, embedder)
    service = BrainService(
        settings=_brain_settings(brain_l1_threshold=0.95, brain_enable_l2=False),
        l1=l1,
    )
    decision = await service.decide("Where is my money?")
    assert decision.route == "l1_hit"
    assert decision.metrics.embed_ms >= 0.0
    assert decision.metrics.redis_knn_ms >= 0.0
    assert decision.metrics.redis_similarity is not None
    assert decision.metrics.qdrant_search_ms is None
    assert decision.metrics.llm_first_token_ms is None


async def test_deflect_metrics_shape_for_l1_only_mode() -> None:
    entries = load_faqs()
    embedder = MockEmbedder(entries)
    l1 = InMemoryL1Router(entries, embedder)
    service = BrainService(
        settings=_brain_settings(brain_l1_threshold=0.95, brain_enable_l2=False),
        l1=l1,
    )
    decision = await service.decide("Please explain card chargeback status")
    assert decision.route == "deflect"
    assert decision.metrics.route == "deflect"
    assert decision.metrics.embed_ms >= 0.0
    assert decision.metrics.redis_knn_ms >= 0.0
    assert decision.metrics.qdrant_search_ms is None
    assert decision.metrics.llm_first_token_ms is None
