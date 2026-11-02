"""Pipecat pipeline assembly (M1-08 to M1-13).

Pipeline chain for bench/file mode:
    transport.input -> Silero VAD -> Deepgram STT -> EchoProcessor
    -> Cartesia TTS -> transport.output
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.frames.frames import Frame, OutputAudioRawFrame, TextFrame
from pipecat.observers.base_observer import BaseObserver
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask
from pipecat.processors.audio.vad_processor import VADProcessor
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.cartesia.tts import CartesiaTTSService
from pipecat.services.deepgram.stt import DeepgramSTTService

from app.agents.echo import EchoProcessor
from app.config import Settings
from app.observers.latency import LatencyObserver


class InMemoryTransportInput(FrameProcessor):
    """Bench input endpoint for raw audio frames."""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)


class InMemoryTransportOutput(FrameProcessor):
    """Bench output endpoint that captures emitted audio/text frames."""

    def __init__(self) -> None:
        super().__init__()
        self.audio_frames: list[OutputAudioRawFrame] = []
        self.text_frames: list[TextFrame] = []

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, OutputAudioRawFrame):
            self.audio_frames.append(frame)
        if isinstance(frame, TextFrame):
            self.text_frames.append(frame)
        await self.push_frame(frame, direction)


@dataclass
class InMemoryTransport:
    """Minimal in-memory transport for offline bench runs (M1-08)."""

    _input: InMemoryTransportInput = field(default_factory=InMemoryTransportInput)
    _output: InMemoryTransportOutput = field(default_factory=InMemoryTransportOutput)

    def input(self) -> InMemoryTransportInput:
        return self._input

    def output(self) -> InMemoryTransportOutput:
        return self._output


@dataclass
class PipelineAssembly:
    """Holds the built pipeline and key processors for runners/tests."""

    pipeline: Pipeline
    transport: InMemoryTransport
    vad: FrameProcessor
    stt: FrameProcessor
    echo: EchoProcessor
    tts: FrameProcessor
    output: InMemoryTransportOutput
    latency_observer: LatencyObserver

    def make_task(self, *, name: str = "voice-agent-bench") -> PipelineTask:
        """Create a task with latency observer attached."""
        observers: list[BaseObserver] = [self.latency_observer]
        return PipelineTask(self.pipeline, name=name, observers=observers)


def _build_default_stt(settings: Settings) -> DeepgramSTTService:
    if not settings.deepgram_api_key:
        raise ValueError("DEEPGRAM_API_KEY is required for Deepgram STT")
    return DeepgramSTTService(
        api_key=settings.deepgram_api_key,
        sample_rate=16_000,
        settings=DeepgramSTTService.Settings(
            model="nova-3",
            interim_results=True,
            smart_format=True,
            punctuate=True,
        ),
    )


def _build_default_tts(settings: Settings) -> CartesiaTTSService:
    if not settings.cartesia_api_key:
        raise ValueError("CARTESIA_API_KEY is required for Cartesia TTS")
    if not settings.cartesia_voice_id:
        raise ValueError("CARTESIA_VOICE_ID is required for Cartesia TTS")
    return CartesiaTTSService(
        api_key=settings.cartesia_api_key,
        voice_id=settings.cartesia_voice_id,
        sample_rate=24_000,
    )


def build_pipeline(
    *,
    settings: Settings | None = None,
    transport: InMemoryTransport | None = None,
    vad_processor: FrameProcessor | None = None,
    stt_processor: FrameProcessor | None = None,
    echo_processor: EchoProcessor | None = None,
    tts_processor: FrameProcessor | None = None,
    vad_silence_seconds: float = 0.8,
) -> PipelineAssembly:
    """Build M1 pipeline chain (M1-09..M1-13) for offline bench mode."""
    cfg = settings or Settings.from_env()
    mem_transport = transport or InMemoryTransport()

    vad = vad_processor or VADProcessor(
        vad_analyzer=SileroVADAnalyzer(
            sample_rate=16_000,
            params=VADParams(stop_secs=vad_silence_seconds),
        )
    )
    stt = stt_processor or _build_default_stt(cfg)
    echo = echo_processor or EchoProcessor()
    tts = tts_processor or _build_default_tts(cfg)
    output = mem_transport.output()

    pipeline = Pipeline([mem_transport.input(), vad, stt, echo, tts, output])
    latency_observer = LatencyObserver(
        vad_silence_ms=vad_silence_seconds * 1000.0,
        echo_processor=echo,
        tts_processor=tts,
        output_processor=output,
    )

    return PipelineAssembly(
        pipeline=pipeline,
        transport=mem_transport,
        vad=vad,
        stt=stt,
        echo=echo,
        tts=tts,
        output=output,
        latency_observer=latency_observer,
    )
