"""Knowledge processor tests (M4B-13/14/16)."""

from __future__ import annotations

import asyncio

import pytest
from pipecat.frames.frames import (
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TextFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection

from app.agents.knowledge import KnowledgeProcessor
from app.brain.types import (
    BrainDecision,
    BrainDeflectFrame,
    BrainMetrics,
    DEFLECT_HANDOFF_TEXT,
)


class _StubBrain:
    def __init__(self, decision: BrainDecision) -> None:
        self._decision = decision
        self.queries: list[str] = []

    async def decide(self, query: str) -> BrainDecision:
        self.queries.append(query)
        return self._decision


def _decision(route: str) -> BrainDecision:
    return BrainDecision(
        route=route,  # type: ignore[arg-type]
        answer_text="answer" if route == "l1_hit" else DEFLECT_HANDOFF_TEXT,
        faq_id="still_processing" if route == "l1_hit" else None,
        metrics=BrainMetrics(
            route=route,  # type: ignore[arg-type]
            embed_ms=1.0,
            redis_knn_ms=1.0,
            redis_similarity=0.9,
        ),
    )


def _final(text: str) -> TranscriptionFrame:
    return TranscriptionFrame(text=text, user_id="u", timestamp="t")


def _agent_texts(pushed: list[object]) -> list[str]:
    return [
        f.text
        for f in pushed
        if isinstance(f, TextFrame) and not isinstance(f, TranscriptionFrame)
    ]


@pytest.mark.asyncio
async def test_knowledge_processor_emits_l1_text_without_deflect_frame() -> None:
    decision = BrainDecision(
        route="l1_hit",
        answer_text="Open Activity to track your transfer.",
        faq_id="where_is_money",
        metrics=BrainMetrics(
            route="l1_hit",
            embed_ms=1.0,
            redis_knn_ms=1.2,
            redis_similarity=0.98,
            brain_ms=2.7,
        ),
    )
    processor = KnowledgeProcessor(_StubBrain(decision))
    pushed: list[object] = []

    async def capture(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append(frame)

    processor.push_frame = capture  # type: ignore[method-assign]
    await processor.process_frame(
        TranscriptionFrame(text="Where is my money?", user_id="u", timestamp="t"),
        FrameDirection.DOWNSTREAM,
    )

    assert isinstance(pushed[0], TranscriptionFrame)
    assert isinstance(pushed[1], LLMFullResponseStartFrame)
    assert isinstance(pushed[2], TextFrame)
    assert pushed[2].text == "Open Activity to track your transfer."
    assert isinstance(pushed[3], LLMFullResponseEndFrame)
    assert not any(isinstance(frame, BrainDeflectFrame) for frame in pushed)


@pytest.mark.asyncio
async def test_knowledge_processor_deflect_emits_handoff_and_deflect_frame() -> None:
    decision = BrainDecision(
        route="deflect",
        answer_text=DEFLECT_HANDOFF_TEXT,
        faq_id=None,
        metrics=BrainMetrics(
            route="deflect",
            embed_ms=1.0,
            redis_knn_ms=1.0,
            redis_similarity=0.12,
            brain_ms=2.0,
        ),
    )
    callbacks = {"count": 0}

    async def on_deflect() -> None:
        callbacks["count"] += 1

    processor = KnowledgeProcessor(_StubBrain(decision), on_deflect=on_deflect)
    pushed: list[object] = []

    async def capture(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append(frame)

    processor.push_frame = capture  # type: ignore[method-assign]
    await processor.process_frame(
        TranscriptionFrame(text="What are your opening hours?", user_id="u", timestamp="t"),
        FrameDirection.DOWNSTREAM,
    )

    agent_texts = [
        f
        for f in pushed
        if isinstance(f, TextFrame) and not isinstance(f, TranscriptionFrame)
    ]
    assert len(agent_texts) == 1
    assert agent_texts[0].text == DEFLECT_HANDOFF_TEXT
    assert any(isinstance(frame, BrainDeflectFrame) for frame in pushed)
    assert callbacks["count"] == 1


def _capturing(processor: KnowledgeProcessor) -> list[object]:
    pushed: list[object] = []

    async def capture(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append(frame)

    processor.push_frame = capture  # type: ignore[method-assign]
    return pushed


@pytest.mark.asyncio
async def test_finals_within_one_turn_are_answered_once_as_one_query() -> None:
    brain = _StubBrain(_decision("l1_hit"))
    processor = KnowledgeProcessor(brain)
    pushed = _capturing(processor)
    down = FrameDirection.DOWNSTREAM

    await processor.process_frame(VADUserStartedSpeakingFrame(), down)
    await processor.process_frame(_final("Why is my payment"), down)
    await processor.process_frame(VADUserStoppedSpeakingFrame(), down)
    await processor.process_frame(_final("still not processing?"), down)

    assert brain.queries == ["Why is my payment still not processing?"]
    assert _agent_texts(pushed) == ["answer"]


@pytest.mark.asyncio
async def test_final_before_vad_stop_is_answered_after_settle() -> None:
    brain = _StubBrain(_decision("l1_hit"))
    processor = KnowledgeProcessor(brain, turn_settle_secs=0.01)
    pushed = _capturing(processor)
    down = FrameDirection.DOWNSTREAM

    await processor.process_frame(VADUserStartedSpeakingFrame(), down)
    await processor.process_frame(_final("Where is my money?"), down)
    assert brain.queries == []
    await processor.process_frame(VADUserStoppedSpeakingFrame(), down)
    await asyncio.sleep(0.05)

    assert brain.queries == ["Where is my money?"]
    assert _agent_texts(pushed) == ["answer"]


@pytest.mark.asyncio
async def test_l2_stream_is_pushed_to_tts_as_whole_sentences() -> None:
    async def rest():
        for token in [" can be", " slower.", " Check", " Activity", "."]:
            yield token

    decision = BrainDecision(
        route="l2_rag",
        answer_text="It",
        faq_id="still_processing",
        answer_stream=rest(),
        metrics=_decision("l1_hit").metrics,
    )
    processor = KnowledgeProcessor(_StubBrain(decision))
    pushed = _capturing(processor)

    await processor.process_frame(_final("Is it slower on weekends?"), FrameDirection.DOWNSTREAM)

    assert _agent_texts(pushed) == ["It can be slower.", " Check Activity."]
    assert isinstance(pushed[1], LLMFullResponseStartFrame)
    assert isinstance(pushed[-1], LLMFullResponseEndFrame)


@pytest.mark.asyncio
async def test_no_further_answers_after_deflect() -> None:
    brain = _StubBrain(_decision("deflect"))
    callbacks = {"count": 0}

    async def on_deflect() -> None:
        callbacks["count"] += 1

    processor = KnowledgeProcessor(brain, on_deflect=on_deflect)
    pushed = _capturing(processor)
    down = FrameDirection.DOWNSTREAM

    await processor.process_frame(_final("What are your fees?"), down)
    await processor.process_frame(_final("And opening hours?"), down)

    assert _agent_texts(pushed) == [DEFLECT_HANDOFF_TEXT]
    assert callbacks["count"] == 1
