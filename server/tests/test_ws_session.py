"""WebSocket session deflect-close behavior tests (M4B-14)."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.ws_session import WebSocketPipelineSession


class _FakeWebSocket:
    def __init__(self) -> None:
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1


@pytest.mark.asyncio
async def test_schedule_deflect_close_closes_session_and_websocket() -> None:
    session = WebSocketPipelineSession.__new__(WebSocketPipelineSession)
    session.websocket = _FakeWebSocket()
    session._deflect_close_task = None
    closed = {"count": 0}

    async def close_stub() -> None:
        closed["count"] += 1

    session.close = close_stub  # type: ignore[method-assign]

    await WebSocketPipelineSession.schedule_deflect_close(session, delay_seconds=0.0)
    assert session._deflect_close_task is not None
    await session._deflect_close_task
    assert closed["count"] == 1
    assert session.websocket.close_calls == 1


@pytest.mark.asyncio
async def test_schedule_deflect_close_is_idempotent_while_pending() -> None:
    session = WebSocketPipelineSession.__new__(WebSocketPipelineSession)
    session.websocket = _FakeWebSocket()
    session._deflect_close_task = None
    gate = asyncio.Event()
    closed = {"count": 0}

    async def close_stub() -> None:
        closed["count"] += 1

    async def slow_deflect_close_after(_delay_seconds: float) -> None:
        await gate.wait()
        await close_stub()
        await session.websocket.close()

    session.close = close_stub  # type: ignore[method-assign]
    session._deflect_close_after = slow_deflect_close_after  # type: ignore[method-assign]

    await WebSocketPipelineSession.schedule_deflect_close(session, delay_seconds=0.0)
    first_task = session._deflect_close_task
    await WebSocketPipelineSession.schedule_deflect_close(session, delay_seconds=0.0)
    assert session._deflect_close_task is first_task
    gate.set()
    await first_task
    assert closed["count"] == 1
    assert session.websocket.close_calls == 1


def test_ws_session_uses_knowledge_processor_when_agent_mode_brain(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeRunner:
        def __init__(self, name: str) -> None:
            self.name = name

    class _FakeAssembly:
        def __init__(self, agent) -> None:
            self.echo = agent

        def make_task(self, *, name: str):
            return SimpleNamespace(name=name)

    def fake_build_pipeline(*, settings, echo_processor):
        captured["settings"] = settings
        captured["agent"] = echo_processor
        return _FakeAssembly(echo_processor)

    monkeypatch.setattr("app.ws_session.PipelineRunner", _FakeRunner)
    monkeypatch.setattr("app.ws_session.build_pipeline", fake_build_pipeline)
    monkeypatch.setattr("app.config.Settings.from_env", lambda: SimpleNamespace(agent_mode="brain"))
    monkeypatch.setattr("app.brain.decision.build_brain_service", lambda settings: object())

    session = WebSocketPipelineSession(_FakeWebSocket())
    assert session.assembly.echo.__class__.__name__ == "KnowledgeProcessor"
    assert captured["agent"].__class__.__name__ == "KnowledgeProcessor"


def test_ws_session_uses_echo_processor_when_agent_mode_echo(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeRunner:
        def __init__(self, name: str) -> None:
            self.name = name

    class _FakeAssembly:
        def __init__(self, agent) -> None:
            self.echo = agent

        def make_task(self, *, name: str):
            return SimpleNamespace(name=name)

    def fake_build_pipeline(*, settings, echo_processor):
        captured["settings"] = settings
        captured["agent"] = echo_processor
        return _FakeAssembly(echo_processor)

    monkeypatch.setattr("app.ws_session.PipelineRunner", _FakeRunner)
    monkeypatch.setattr("app.ws_session.build_pipeline", fake_build_pipeline)
    monkeypatch.setattr("app.config.Settings.from_env", lambda: SimpleNamespace(agent_mode="echo"))

    session = WebSocketPipelineSession(_FakeWebSocket())
    assert session.assembly.echo.__class__.__name__ == "EchoProcessor"
    assert captured["agent"].__class__.__name__ == "EchoProcessor"
