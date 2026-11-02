"""Pipeline assembly tests (M1-08 to M1-13)."""

from __future__ import annotations

from pipecat.frames.frames import TextFrame, TranscriptionFrame, TTSAudioRawFrame, UserAudioRawFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.tests.utils import run_test

from app.agents.echo import EchoProcessor
from app.pipeline import InMemoryTransport, build_pipeline


class _PassthroughProcessor(FrameProcessor):
    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)


class _FakeSTT(FrameProcessor):
    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, UserAudioRawFrame):
            await self.push_frame(
                TranscriptionFrame(text="hello", user_id="u", timestamp="t"),
                direction,
            )


class _FakeTTS(FrameProcessor):
    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        await self.push_frame(frame, direction)
        if isinstance(frame, TextFrame) and frame.text.startswith("I heard you say: "):
            await self.push_frame(
                TTSAudioRawFrame(audio=b"\x00\x00", sample_rate=24000, num_channels=1),
                direction,
            )


def test_build_pipeline_in_memory_components() -> None:
    assembly = build_pipeline(
        transport=InMemoryTransport(),
        vad_processor=_PassthroughProcessor(),
        stt_processor=_PassthroughProcessor(),
        echo_processor=EchoProcessor(),
        tts_processor=_PassthroughProcessor(),
    )

    assert assembly.transport.input() is not None
    assert assembly.transport.output() is assembly.output
    assert assembly.echo.__class__.__name__ == "EchoProcessor"
    assert assembly.latency_observer is not None


def test_minimal_audio_to_text_to_audio_flow() -> None:
    assembly = build_pipeline(
        transport=InMemoryTransport(),
        vad_processor=_PassthroughProcessor(),
        stt_processor=_FakeSTT(),
        echo_processor=EchoProcessor(),
        tts_processor=_FakeTTS(),
    )

    down, _ = run_sync_test(
        assembly.pipeline,
        UserAudioRawFrame(audio=b"\x00" * 640, sample_rate=16000, num_channels=1),
    )

    assert any(isinstance(f, TranscriptionFrame) for f in down)
    assert any(isinstance(f, TextFrame) and f.text == "I heard you say: hello" for f in down)
    assert any(isinstance(f, TTSAudioRawFrame) for f in down)


def run_sync_test(processor: FrameProcessor, frame):
    import asyncio

    return asyncio.run(run_test(processor, frames_to_send=[frame], send_end_frame=True))

