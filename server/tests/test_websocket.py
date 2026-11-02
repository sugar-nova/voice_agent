from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


class _FakeSession:
    created: list["_FakeSession"] = []

    def __init__(self, websocket) -> None:
        self.websocket = websocket
        self.started = False
        self.closed = False
        self.audio_samples: list[tuple[bytes, int]] = []
        self.playback_marks: list[tuple[int, int]] = []
        _FakeSession.created.append(self)

    async def start(self) -> None:
        self.started = True
        await self.websocket.send_json({"type": "ready"})

    async def handle_audio(self, audio: bytes, sample_rate: int) -> None:
        self.audio_samples.append((audio, sample_rate))

    def mark_playback_started(self, turn_id: int, played_at_ms: int) -> None:
        self.playback_marks.append((turn_id, played_at_ms))

    async def close(self) -> None:
        self.closed = True


def test_ws_rejects_invalid_first_message(monkeypatch) -> None:
    monkeypatch.setattr("app.main.WebSocketPipelineSession", _FakeSession)
    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_text("not-json")
            data = ws.receive_json()
            assert data["type"] == "error"
            assert "start" in data["message"].lower()


def test_ws_accepts_start_audio_ping_playback_started_and_stop(monkeypatch) -> None:
    _FakeSession.created.clear()
    monkeypatch.setattr("app.main.WebSocketPipelineSession", _FakeSession)

    with TestClient(app) as client:
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "start", "sampleRate": 16000})
            assert ws.receive_json() == {"type": "ready"}

            ws.send_bytes(b"\x00\x01")
            ws.send_json({"type": "ping", "pingId": "p1", "sentAtMs": 123})
            assert ws.receive_json() == {"type": "pong", "pingId": "p1", "sentAtMs": 123}

            ws.send_json({"type": "playback_started", "turnId": 7, "playedAtMs": 456})
            ws.send_json({"type": "stop"})

    assert len(_FakeSession.created) == 1
    session = _FakeSession.created[0]
    assert session.started
    assert session.closed
    assert session.audio_samples == [(b"\x00\x01", 16000)]
    assert session.playback_marks == [(7, 456)]
