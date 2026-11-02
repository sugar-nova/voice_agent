"""Per-turn latency timestamps t0–t4 (M1-05 / M1-06 / M1-07).

Plan §6 event → field mapping:
  t0  User speech ended (VAD)     → VADUserStoppedSpeakingFrame, UserStoppedSpeakingFrame
  t1  STT final transcript       → TranscriptionFrame (not InterimTranscriptionFrame)
  t2  Echo agent text out        → TextFrame from EchoProcessor ("I heard you say: …")
  t3  TTS first audio chunk      → TTSAudioRawFrame (from TTS processor / first after t2)
  t4  First outbound audio       → TTSAudioRawFrame reaching output transport processor
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pipecat.frames.frames import (
    Frame,
    InterimTranscriptionFrame,
    OutputAudioRawFrame,
    TextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    UserStoppedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from app.agents.echo import ECHO_PREFIX, EchoProcessor, is_final_transcription
from app.schemas import LatencyStages

if TYPE_CHECKING:
    pass

logger = logging.getLogger("voice_agent.latency")


@dataclass
class TurnLatencyRecord:
    """In-memory latency snapshot for one user turn."""

    turn_id: int
    stages: LatencyStages
    vad_silence_ms: float | None = None


@dataclass
class TurnLatencyTracker:
    """Records t0–t4 for the active turn; completes when all five are set."""

    vad_silence_ms: float | None = None
    _next_turn_id: int = 1
    _current: TurnLatencyRecord | None = field(default=None, init=False)
    completed: list[TurnLatencyRecord] = field(default_factory=list, init=False)

    def active_turn(self) -> TurnLatencyRecord | None:
        return self._current

    def begin_turn_at_t0(self, t0: float) -> TurnLatencyRecord:
        if self._current is not None:
            if self._current.stages.t0 is None:
                self._current.stages.t0 = t0
                self._maybe_complete_turn()
            return self._current

        record = TurnLatencyRecord(
            turn_id=self._next_turn_id,
            stages=LatencyStages(t0=t0),
            vad_silence_ms=self.vad_silence_ms,
        )
        self._next_turn_id += 1
        self._current = record
        return record

    def mark_t1(self, t1: float) -> None:
        self._set_stage("t1", t1)

    def mark_t2(self, t2: float) -> None:
        self._set_stage("t2", t2)

    def mark_t3(self, t3: float) -> None:
        self._set_stage("t3", t3)

    def mark_t4(self, t4: float) -> None:
        self._set_stage("t4", t4)

    def _set_stage(self, name: str, value: float) -> None:
        self._ensure_current()
        if self._current is None:
            return
        stages = self._current.stages
        if getattr(stages, name) is not None:
            return
        setattr(stages, name, value)
        self._maybe_complete_turn()

    def _ensure_current(self) -> None:
        if self._current is not None:
            return
        record = TurnLatencyRecord(
            turn_id=self._next_turn_id,
            stages=LatencyStages(),
            vad_silence_ms=self.vad_silence_ms,
        )
        self._next_turn_id += 1
        self._current = record

    def _maybe_complete_turn(self) -> TurnLatencyRecord | None:
        if self._current is None:
            return None
        s = self._current.stages
        if None in (s.t0, s.t1, s.t2, s.t3, s.t4):
            return None
        record = self._current
        self.completed.append(record)
        self._current = None
        emit_turn_log_line(record)
        return record

    def handle_push(
        self,
        data: FramePushed,
        *,
        echo_processor: FrameProcessor | None = None,
        tts_processor: FrameProcessor | None = None,
        output_processor: FrameProcessor | None = None,
        timestamp: float | None = None,
    ) -> TurnLatencyRecord | None:
        """Update turn state from an observed frame push (M1-06)."""
        ts = timestamp if timestamp is not None else time.monotonic()
        frame = data.frame

        if isinstance(frame, (VADUserStoppedSpeakingFrame, UserStoppedSpeakingFrame)):
            self.begin_turn_at_t0(ts)
            return None

        if is_final_transcription(frame):
            self.mark_t1(ts)

        elif isinstance(frame, TextFrame) and _is_echo_agent_text(
            frame, source=data.source, echo_processor=echo_processor
        ):
            self.mark_t2(ts)

        elif isinstance(frame, TTSAudioRawFrame):
            if self._current and self._current.stages.t2 is not None and self._current.stages.t3 is None:
                if tts_processor is None or data.source is tts_processor:
                    self.mark_t3(ts)

        if isinstance(frame, OutputAudioRawFrame):
            if self._current and self._current.stages.t3 is not None and self._current.stages.t4 is None:
                if output_processor is None:
                    if data.source is not tts_processor:
                        self.mark_t4(ts)
                elif data.source is output_processor:
                    self.mark_t4(ts)

        return None


def _is_echo_agent_text(
    frame: TextFrame,
    *,
    source: FrameProcessor,
    echo_processor: FrameProcessor | None,
) -> bool:
    if echo_processor is not None and source is not echo_processor:
        return False
    if frame.text.startswith(ECHO_PREFIX):
        return True
    # Knowledge brain agent (plain FAQ answers)
    return source.__class__.__name__ == "KnowledgeProcessor"


def turn_log_payload(record: TurnLatencyRecord) -> dict[str, Any]:
    """JSON-serializable payload for one turn (M1-07)."""
    return {
        "event": "turn_latency",
        "turnId": record.turn_id,
        "stages": record.stages.model_dump(),
        "vad_silence_ms": record.vad_silence_ms,
    }


def emit_turn_log_line(record: TurnLatencyRecord) -> str:
    """Emit one JSON log line per completed turn; parseable with jq."""
    line = json.dumps(turn_log_payload(record), separators=(",", ":"))
    logger.info(line)
    return line


class LatencyObserver(BaseObserver):
    """Pipecat observer that fills TurnLatencyTracker from pipeline frame flow."""

    def __init__(
        self,
        *,
        vad_silence_ms: float | None = None,
        echo_processor: FrameProcessor | None = None,
        tts_processor: FrameProcessor | None = None,
        output_processor: FrameProcessor | None = None,
        tracker: TurnLatencyTracker | None = None,
        **kwargs,
    ) -> None:
        super().__init__(observe_every_push=True, **kwargs)
        self._tracker = tracker or TurnLatencyTracker(vad_silence_ms=vad_silence_ms)
        self._echo_processor = echo_processor
        self._tts_processor = tts_processor
        self._output_processor = output_processor

    @property
    def tracker(self) -> TurnLatencyTracker:
        return self._tracker

    async def on_push_frame(self, data: FramePushed) -> None:
        if data.direction is not FrameDirection.DOWNSTREAM:
            return
        self._tracker.handle_push(
            data,
            echo_processor=self._echo_processor,
            tts_processor=self._tts_processor,
            output_processor=self._output_processor,
        )
