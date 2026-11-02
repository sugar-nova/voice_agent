"""Smoke tests for shared schemas (M1-01)."""

from app.schemas import (
    AgentTextMessage,
    BrainMetricsPayload,
    LatencyStages,
    MetricsMessage,
    TranscriptMessage,
    agent_text_payload,
    metrics_payload,
)


def test_schemas_importable_from_echo_and_observer_paths() -> None:
    from app.agents import echo  # noqa: F401
    from app.observers import latency  # noqa: F401

    assert echo.format_echo_response("x")


def test_metrics_payload_shape() -> None:
    stages = LatencyStages(t0=1.0, t1=1.1, t2=1.11, t3=1.5, t4=1.6)
    data = metrics_payload(7, stages, vad_silence_ms=400.0)
    parsed = MetricsMessage.model_validate(data)
    assert parsed.turnId == 7
    assert parsed.stages.t3 == 1.5
    assert parsed.vad_silence_ms == 400.0


def test_metrics_payload_with_brain_block() -> None:
    stages = LatencyStages(t0=1.0, t1=1.1, t2=1.2, t3=1.3, t4=1.4)
    brain = BrainMetricsPayload(
        route="l1_hit",
        embed_ms=2.1,
        redis_knn_ms=1.4,
        redis_similarity=0.97,
        brain_ms=4.2,
    )
    data = metrics_payload(
        11,
        stages,
        vad_silence_ms=400.0,
        brain=brain.model_dump(),
        clientPlayedAtMs=123,
    )
    parsed = MetricsMessage.model_validate(data)
    assert parsed.extra.brain is not None
    assert parsed.extra.brain.route == "l1_hit"
    assert parsed.extra.clientPlayedAtMs == 123


def test_transcript_and_agent_text_messages() -> None:
    t = TranscriptMessage(text="hi", final=True)
    assert t.model_dump() == {"type": "transcript", "text": "hi", "final": True}
    assert agent_text_payload("I heard you say: hi") == {
        "type": "agent_text",
        "text": "I heard you say: hi",
    }
    assert AgentTextMessage(text="ok").text == "ok"
