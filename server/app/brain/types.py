"""Brain routing types and session frames (M4B)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any, Literal

from pipecat.frames.frames import Frame

BrainRoute = Literal["l1_hit", "l2_rag", "deflect"]

DEFLECT_HANDOFF_TEXT = (
    "I can only help with questions about where your money is — "
    "let me connect you to a human. Goodbye."
)


@dataclass(frozen=True)
class BrainMetrics:
    route: BrainRoute
    embed_ms: float
    redis_knn_ms: float
    redis_similarity: float | None
    qdrant_search_ms: float | None = None
    llm_first_token_ms: float | None = None
    brain_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "route": self.route,
            "embed_ms": round(self.embed_ms, 3),
            "redis_knn_ms": round(self.redis_knn_ms, 3),
            "redis_similarity": self.redis_similarity,
            "qdrant_search_ms": self.qdrant_search_ms,
            "llm_first_token_ms": self.llm_first_token_ms,
            "brain_ms": round(self.brain_ms, 3),
        }


@dataclass(frozen=True)
class BrainDecision:
    route: BrainRoute
    answer_text: str
    metrics: BrainMetrics
    faq_id: str | None = None
    # l2_rag only: the rest of the streamed answer after answer_text.
    answer_stream: AsyncGenerator[str, None] | None = None


class BrainDeflectFrame(Frame):
    """Signal that the session should end after deflection TTS (M4B-14)."""

    def __init__(self) -> None:
        super().__init__()
