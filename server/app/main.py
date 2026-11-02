"""FastAPI entrypoint."""

import json
import logging
from typing import Any

from fastapi import FastAPI, WebSocket
from fastapi.websockets import WebSocketDisconnect

from app.config import Settings
from app.schemas import (
    ClientPingMessage,
    ClientPlaybackStartedMessage,
    ClientStartMessage,
)

try:
    from app.ws_session import WebSocketPipelineSession as _DefaultWebSocketPipelineSession
except Exception:
    _DefaultWebSocketPipelineSession = None

WebSocketPipelineSession: Any = _DefaultWebSocketPipelineSession

app = FastAPI(title="voice-agent-server")


@app.on_event("startup")
def log_config() -> None:
    settings = Settings.from_env()
    logging.getLogger("voice_agent.config").info(settings.log_summary())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    session: Any = None

    try:
        if WebSocketPipelineSession is None:
            await websocket.send_json({"type": "error", "message": "Server session unavailable"})
            await websocket.close(code=1011)
            return

        first = await websocket.receive_text()
        try:
            payload = json.loads(first)
            start = ClientStartMessage.model_validate(payload)
        except Exception:
            await websocket.send_json({"type": "error", "message": "First message must be valid start"})
            await websocket.close(code=1008)
            return

        session = WebSocketPipelineSession(websocket)
        await session.start()

        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break

            if "bytes" in message and message["bytes"] is not None:
                await session.handle_audio(message["bytes"], sample_rate=start.sampleRate)
                continue

            if "text" in message and message["text"]:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue

                msg_type = data.get("type")
                if msg_type == "ping":
                    ping = ClientPingMessage.model_validate(data)
                    await websocket.send_json(
                        {"type": "pong", "pingId": ping.pingId, "sentAtMs": ping.sentAtMs}
                    )
                elif msg_type == "playback_started":
                    playback_started = ClientPlaybackStartedMessage.model_validate(data)
                    session.mark_playback_started(
                        turn_id=playback_started.turnId,
                        played_at_ms=playback_started.playedAtMs,
                    )
                elif msg_type == "stop":
                    break

    except WebSocketDisconnect:
        return
    finally:
        if session is not None:
            await session.close()
        try:
            await websocket.close()
        except Exception:
            pass
