"""Shared message and event types (M1-01)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


# --- WebSocket JSON (plan §4.4) ---


class ClientStartMessage(BaseModel):
    type: Literal["start"] = "start"
    sampleRate: int = Field(..., ge=8000, le=48000)


class ClientStopMessage(BaseModel):
    type: Literal["stop"] = "stop"


class ClientPingMessage(BaseModel):
    type: Literal["ping"] = "ping"
    pingId: str
    sentAtMs: int


class ClientPlaybackStartedMessage(BaseModel):
    type: Literal["playback_started"] = "playback_started"
    turnId: int
    playedAtMs: int


class ServerReadyMessage(BaseModel):
    type: Literal["ready"] = "ready"


class TranscriptMessage(BaseModel):
    type: Literal["transcript"] = "transcript"
    text: str
    final: bool


class AgentTextMessage(BaseModel):
    type: Literal["agent_text"] = "agent_text"
    text: str


class InterruptMessage(BaseModel):
    type: Literal["interrupt"] = "interrupt"


class ErrorMessage(BaseModel):
    type: Literal["error"] = "error"
    message: str


class PongMessage(BaseModel):
    type: Literal["pong"] = "pong"
    pingId: str
    sentAtMs: int


class LatencyStages(BaseModel):
    """Server-side turn timestamps (plan §6). Values are epoch seconds or monotonic marks."""

    t0: float | None = None
    t1: float | None = None
    t2: float | None = None
    t3: float | None = None
    t4: float | None = None


class BrainMetricsPayload(BaseModel):
    """Optional brain block in metrics extra (M4B-18)."""

    route: Literal["l1_hit", "l2_rag", "deflect"]
    embed_ms: float
    redis_knn_ms: float
    redis_similarity: float | None = None
    qdrant_search_ms: float | None = None
    llm_first_token_ms: float | None = None
    brain_ms: float


class MetricsExtraPayload(BaseModel):
    """Typed metrics extra payload with room for future keys."""

    model_config = ConfigDict(extra="allow")
    clientPlayedAtMs: int | None = None
    brain: BrainMetricsPayload | None = None


class MetricsMessage(BaseModel):
    type: Literal["metrics"] = "metrics"
    turnId: int
    stages: LatencyStages
    vad_silence_ms: float | None = None
    extra: MetricsExtraPayload = Field(default_factory=MetricsExtraPayload)


ClientMessage = (
    ClientStartMessage
    | ClientStopMessage
    | ClientPingMessage
    | ClientPlaybackStartedMessage
)
ServerEventMessage = (
    ServerReadyMessage
    | TranscriptMessage
    | AgentTextMessage
    | InterruptMessage
    | MetricsMessage
    | ErrorMessage
    | PongMessage
)


def agent_text_payload(text: str) -> dict[str, Any]:
    """Serialize agent text for WebSocket or logging."""
    return AgentTextMessage(text=text).model_dump()


def metrics_payload(
    turn_id: int,
    stages: LatencyStages,
    *,
    vad_silence_ms: float | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Serialize per-turn metrics (plan §6)."""
    return MetricsMessage(
        turnId=turn_id,
        stages=stages,
        vad_silence_ms=vad_silence_ms,
        extra=extra,
    ).model_dump()
