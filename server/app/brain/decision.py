"""Combine L1 / L2 / deflect gates (M4B-13)."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncGenerator

from app.brain.l1 import InMemoryL1Router, L1LookupResult
from app.brain.l2 import L2Retriever
from app.brain.llm import NOT_COVERED, L2Synthesizer
from app.brain.types import DEFLECT_HANDOFF_TEXT, BrainDecision, BrainMetrics
from app.config import Settings

logger = logging.getLogger("voice_agent.brain")

L2_TOP_K = 3


class BrainService:
    def __init__(
        self,
        *,
        settings: Settings,
        l1: InMemoryL1Router,
        l2: L2Retriever | None = None,
        llm: L2Synthesizer | None = None,
    ) -> None:
        self._settings = settings
        self._l1 = l1
        self._l2 = l2
        self._llm = llm

    async def decide(self, query: str) -> BrainDecision:
        t0 = time.perf_counter()
        l1 = self._l1.lookup(query)
        if l1.similarity >= self._settings.brain_l1_threshold and l1.entry is not None:
            return BrainDecision(
                route="l1_hit",
                answer_text=l1.entry.answer,
                faq_id=l1.entry.id,
                metrics=_metrics(l1, "l1_hit", t0),
            )

        if (
            not self._settings.brain_enable_l2
            or self._l2 is None
            or self._llm is None
            or l1.query_vec is None
        ):
            return _deflect(l1, t0)

        t_search = time.perf_counter()
        chunks = self._l2.search(l1.query_vec, L2_TOP_K)
        search_ms = (time.perf_counter() - t_search) * 1000.0
        if not chunks or chunks[0].score < self._settings.brain_l2_relevance_floor:
            return _deflect(l1, t0, qdrant_search_ms=search_ms)

        stream = self._llm.stream(query, chunks)
        try:
            head, first_token_ms = await _read_head(stream)
        except Exception as exc:
            logger.warning("L2 LLM failed (%s); deflecting", exc)
            await stream.aclose()
            return _deflect(l1, t0, qdrant_search_ms=search_ms)

        if head is None:
            await stream.aclose()
            return _deflect(
                l1, t0, qdrant_search_ms=search_ms, llm_first_token_ms=first_token_ms
            )

        return BrainDecision(
            route="l2_rag",
            answer_text=head,
            faq_id=chunks[0].faq_id,
            answer_stream=stream,
            metrics=_metrics(
                l1,
                "l2_rag",
                t0,
                qdrant_search_ms=search_ms,
                llm_first_token_ms=first_token_ms,
            ),
        )


async def _read_head(stream: AsyncGenerator[str, None]) -> tuple[str | None, float | None]:
    """Read tokens until the reply is clearly an answer (returns text so far) or NOT_COVERED (None)."""
    t0 = time.perf_counter()
    first_token_ms: float | None = None
    text = ""
    async for token in stream:
        if first_token_ms is None:
            first_token_ms = (time.perf_counter() - t0) * 1000.0
        text += token
        head = text.lstrip()
        if not head:
            continue
        if head.startswith(NOT_COVERED):
            return None, first_token_ms
        if not NOT_COVERED.startswith(head):
            return text, first_token_ms
    return None, first_token_ms


def _metrics(
    l1: L1LookupResult,
    route: str,
    t0: float,
    *,
    qdrant_search_ms: float | None = None,
    llm_first_token_ms: float | None = None,
) -> BrainMetrics:
    return BrainMetrics(
        route=route,  # type: ignore[arg-type]
        embed_ms=l1.embed_ms,
        redis_knn_ms=l1.knn_ms,
        redis_similarity=l1.similarity,
        qdrant_search_ms=qdrant_search_ms,
        llm_first_token_ms=llm_first_token_ms,
        brain_ms=(time.perf_counter() - t0) * 1000.0,
    )


def _deflect(
    l1: L1LookupResult,
    t0: float,
    *,
    qdrant_search_ms: float | None = None,
    llm_first_token_ms: float | None = None,
) -> BrainDecision:
    return BrainDecision(
        route="deflect",
        answer_text=DEFLECT_HANDOFF_TEXT,
        faq_id=None,
        metrics=_metrics(
            l1,
            "deflect",
            t0,
            qdrant_search_ms=qdrant_search_ms,
            llm_first_token_ms=llm_first_token_ms,
        ),
    )


def build_brain_service(settings: Settings) -> BrainService:
    from app.kb.load import load_faqs

    from app.brain.l1 import InMemoryL1Router, try_build_redis_l1_router
    from app.brain.l2 import build_l2_retriever
    from app.brain.llm import OllamaSynthesizer

    entries = load_faqs()
    if settings.embedding_provider != "fastembed":
        raise ValueError(
            "Brain agent requires EMBEDDING_PROVIDER=fastembed and "
            "pip install -e 'server[brain]'"
        )
    try:
        from app.brain.embeddings import FastEmbedder
    except ImportError as exc:
        raise ImportError("Install brain extras: pip install -e 'server[brain]'") from exc

    embedder = FastEmbedder(settings.embedding_model)
    l1: InMemoryL1Router
    if settings.redis_url:
        redis_router = try_build_redis_l1_router(
            entries=entries,
            embedder=embedder,
            redis_url=settings.redis_url,
            index_name=settings.redis_index_name,
        )
        l1 = redis_router or InMemoryL1Router(entries, embedder)
    else:
        l1 = InMemoryL1Router(entries, embedder)

    if not settings.brain_enable_l2:
        return BrainService(settings=settings, l1=l1)

    l2 = build_l2_retriever(
        entries=entries,
        embedder=embedder,
        qdrant_url=settings.qdrant_url,
        collection=settings.qdrant_collection,
    )
    llm = OllamaSynthesizer(url=settings.ollama_url, model=settings.ollama_model)
    return BrainService(settings=settings, l1=l1, l2=l2, llm=llm)
