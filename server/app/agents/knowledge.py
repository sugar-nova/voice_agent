"""FAQ brain processor — replaces echo when agent=brain (M4B-15)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator, Awaitable, Callable

from pipecat.frames.frames import (
    EndFrame,
    Frame,
    InterimTranscriptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TextFrame,
    TranscriptionFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from app.brain.decision import BrainService
from app.brain.types import BrainDeflectFrame, BrainDecision, BrainMetrics

logger = logging.getLogger("voice_agent.brain")

# Deepgram may deliver the last final of a turn just before VAD stop; the
# finalize response for any remaining audio usually lands within this window.
TURN_SETTLE_SECS = 0.25

_SENTENCE_ENDINGS = (".", "!", "?")


class KnowledgeProcessor(FrameProcessor):
    """Answers once per user turn.

    Deepgram emits a final ``TranscriptionFrame`` per speech segment, so a pause
    mid-question yields several finals. They are buffered until VAD reports the
    user stopped speaking, then routed as one query.
    """

    def __init__(
        self,
        brain: BrainService,
        *,
        on_deflect: Callable[[], Awaitable[None]] | None = None,
        turn_settle_secs: float = TURN_SETTLE_SECS,
    ) -> None:
        super().__init__()
        self._brain = brain
        self._on_deflect = on_deflect
        self._turn_settle_secs = turn_settle_secs
        self._user_speaking = False
        self._pending: list[str] = []
        self._settle_task: asyncio.Task[None] | None = None
        self._deflected = False
        self.last_decision: BrainDecision | None = None
        self.last_metrics: BrainMetrics | None = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, InterimTranscriptionFrame):
            frame.skip_tts = True
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame):
            frame.skip_tts = True
            await self.push_frame(frame, direction)
            text = frame.text.strip()
            if not text or self._deflected:
                return
            self._pending.append(text)
            if not self._user_speaking:
                self._cancel_settle()
                await self._answer_turn()
            return

        if isinstance(frame, VADUserStartedSpeakingFrame):
            self._user_speaking = True
            self._cancel_settle()
        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            self._user_speaking = False
            if self._pending:
                self._cancel_settle()
                self._settle_task = asyncio.create_task(self._settle_then_answer())
        elif isinstance(frame, EndFrame):
            self._cancel_settle()

        await self.push_frame(frame, direction)

    def _cancel_settle(self) -> None:
        if self._settle_task is not None and not self._settle_task.done():
            self._settle_task.cancel()
        self._settle_task = None

    async def _settle_then_answer(self) -> None:
        await asyncio.sleep(self._turn_settle_secs)
        self._settle_task = None
        await self._answer_turn()

    async def _answer_turn(self) -> None:
        if not self._pending or self._deflected:
            return
        query = " ".join(self._pending)
        self._pending = []
        direction = FrameDirection.DOWNSTREAM

        decision = await self._brain.decide(query)
        self.last_decision = decision
        self.last_metrics = decision.metrics

        await self.push_frame(LLMFullResponseStartFrame(), direction)
        if decision.answer_stream is None:
            await self.push_frame(TextFrame(text=decision.answer_text), direction)
        else:
            await self._push_streamed_answer(decision.answer_text, decision.answer_stream)
        await self.push_frame(LLMFullResponseEndFrame(), direction)

        if decision.route == "deflect":
            self._deflected = True
            await self.push_frame(BrainDeflectFrame(), direction)
            if self._on_deflect is not None:
                await self._on_deflect()

    async def _push_streamed_answer(self, head: str, stream: AsyncGenerator[str, None]) -> None:
        buffer = head
        try:
            async for token in stream:
                buffer += token
                if buffer.rstrip().endswith(_SENTENCE_ENDINGS):
                    await self.push_frame(TextFrame(text=buffer), FrameDirection.DOWNSTREAM)
                    buffer = ""
        except Exception as exc:
            logger.warning("L2 answer stream failed mid-answer (%s)", exc)
        if buffer.strip():
            await self.push_frame(TextFrame(text=buffer), FrameDirection.DOWNSTREAM)
