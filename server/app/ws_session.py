from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect
from pipecat.frames.frames import (
    EndFrame,
    Frame,
    InterimTranscriptionFrame,
    OutputAudioRawFrame,
    TextFrame,
    TranscriptionFrame,
    UserAudioRawFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed
from pipecat.pipeline.runner import PipelineRunner
from pipecat.processors.frame_processor import FrameDirection

from app.pipeline import build_pipeline
from app.schemas import BrainMetricsPayload, LatencyStages
from app.brain.types import BrainDeflectFrame


@dataclass
class _ClientTiming:
  played_at_ms: int


class _WebSocketPipelineObserver(BaseObserver):
  def __init__(self, *, session: "WebSocketPipelineSession") -> None:
    super().__init__(observe_every_push=True)
    self._session = session
    self._sent_metrics_count = 0

  async def on_push_frame(self, data: FramePushed) -> None:
    if data.direction is not FrameDirection.DOWNSTREAM:
      return

    frame = data.frame

    if isinstance(frame, InterimTranscriptionFrame) and data.source is self._session.assembly.stt:
      await self._session.send_json({"type": "transcript", "text": frame.text, "final": False})
    elif isinstance(frame, TranscriptionFrame) and data.source is self._session.assembly.stt:
      await self._session.send_json({"type": "transcript", "text": frame.text, "final": True})
    elif (
      isinstance(frame, TextFrame)
      and data.source is self._session.assembly.echo
      and not getattr(frame, "skip_tts", False)
    ):
      await self._session.send_json({"type": "agent_text", "text": frame.text})
    elif isinstance(frame, BrainDeflectFrame):
      await self._session.schedule_deflect_close()
    elif isinstance(frame, OutputAudioRawFrame) and data.source is self._session.assembly.output:
      await self._session.send_bytes(frame.audio)

    if frame.__class__.__name__.lower().find("interrupt") >= 0:
      await self._session.send_json({"type": "interrupt"})

    await self._emit_new_metrics()

  async def _emit_new_metrics(self) -> None:
    completed = self._session.assembly.latency_observer.tracker.completed
    while self._sent_metrics_count < len(completed):
      record = completed[self._sent_metrics_count]
      self._sent_metrics_count += 1
      payload = {
        "type": "metrics",
        "turnId": record.turn_id,
        "stages": record.stages.model_dump(),
        "vad_silence_ms": record.vad_silence_ms,
        "extra": {},
      }
      client_timing = self._session.client_timing_for_turn(record.turn_id)
      if client_timing is not None:
        payload["extra"]["clientPlayedAtMs"] = client_timing.played_at_ms
      agent = self._session.assembly.echo
      if hasattr(agent, "last_metrics") and agent.last_metrics is not None:
        payload["extra"]["brain"] = BrainMetricsPayload.model_validate(
          agent.last_metrics.to_dict()
        ).model_dump()
      await self._session.send_json(payload)


class WebSocketPipelineSession:
  def __init__(self, websocket: WebSocket) -> None:
    from app.agents.echo import EchoProcessor
    from app.agents.knowledge import KnowledgeProcessor
    from app.brain.decision import build_brain_service
    from app.config import Settings

    self.websocket = websocket
    settings = Settings.from_env()
    self._deflect_close_task: asyncio.Task[None] | None = None
    if settings.agent_mode == "brain":
      brain = build_brain_service(settings)
      agent = KnowledgeProcessor(brain, on_deflect=self._handle_deflect)
    else:
      agent = EchoProcessor()
    self.assembly = build_pipeline(settings=settings, echo_processor=agent)
    self.task = self.assembly.make_task(name="m3-ws-session")
    self.runner = PipelineRunner(name="m3-ws-session")
    self._runner_task: asyncio.Task[None] | None = None
    self._send_lock = asyncio.Lock()
    self._client_playback: dict[int, _ClientTiming] = {}

  async def schedule_deflect_close(self, *, delay_seconds: float = 8.0) -> None:
    if self._deflect_close_task is not None and not self._deflect_close_task.done():
      return
    self._deflect_close_task = asyncio.create_task(self._deflect_close_after(delay_seconds))

  async def _handle_deflect(self) -> None:
    await self.schedule_deflect_close()

  async def _deflect_close_after(self, delay_seconds: float) -> None:
    await asyncio.sleep(delay_seconds)
    await self.close()
    try:
      await self.websocket.close()
    except Exception:
      pass

  async def start(self) -> None:
    self.task.add_observer(_WebSocketPipelineObserver(session=self))
    self._runner_task = asyncio.create_task(self.runner.run(self.task))
    await self.send_json({"type": "ready"})

  async def handle_audio(self, audio: bytes, sample_rate: int) -> None:
    await self.task.queue_frame(
      UserAudioRawFrame(audio=audio, sample_rate=sample_rate, num_channels=1)
    )

  def mark_playback_started(self, turn_id: int, played_at_ms: int) -> None:
    self._client_playback[turn_id] = _ClientTiming(played_at_ms=played_at_ms)

  def client_timing_for_turn(self, turn_id: int) -> _ClientTiming | None:
    return self._client_playback.get(turn_id)

  async def send_json(self, payload: dict[str, Any]) -> None:
    async with self._send_lock:
      await self.websocket.send_json(payload)

  async def send_bytes(self, payload: bytes) -> None:
    async with self._send_lock:
      await self.websocket.send_bytes(payload)

  async def close(self) -> None:
    await self.task.queue_frame(EndFrame())
    if self._runner_task is not None:
      try:
        await self._runner_task
      except Exception:
        pass


async def run_websocket_session(websocket: WebSocket, sample_rate: int) -> None:
  session = WebSocketPipelineSession(websocket)
  await session.start()

  try:
    while True:
      message = await websocket.receive()
      if message.get("type") == "websocket.disconnect":
        break
      if "bytes" in message and message["bytes"] is not None:
        await session.handle_audio(message["bytes"], sample_rate=sample_rate)
        continue
      if "text" in message and message["text"]:
        # Text events are handled by endpoint before session starts; ignore here.
        continue
  except WebSocketDisconnect:
    pass
  finally:
    await session.close()
