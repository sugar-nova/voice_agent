"""Echo agent processor (M1-02 / M1-03)."""

from __future__ import annotations

from pipecat.frames.frames import (
    Frame,
    InterimTranscriptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

ECHO_PREFIX = "I heard you say: "


def format_echo_response(transcript: str) -> str | None:
    """Return agent reply text, or None if the final transcript is empty."""
    text = transcript.strip()
    if not text:
        return None
    return f"{ECHO_PREFIX}{text}"


def is_final_transcription(frame: Frame) -> bool:
    """True for STT final transcripts (not interim partials)."""
    if isinstance(frame, InterimTranscriptionFrame):
        return False
    return isinstance(frame, TranscriptionFrame)


class EchoProcessor(FrameProcessor):
    """Pass through non-final STT; on final transcript emit TTS-bound TextFrame."""

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, InterimTranscriptionFrame):
            frame.skip_tts = True
            await self.push_frame(frame, direction)
            return

        if isinstance(frame, TranscriptionFrame):
            frame.skip_tts = True
            await self.push_frame(frame, direction)
            reply = format_echo_response(frame.text)
            if reply is not None:
                # TTS holds the last sentence until it sees the response end frame.
                await self.push_frame(LLMFullResponseStartFrame(), direction)
                await self.push_frame(TextFrame(text=reply), direction)
                await self.push_frame(LLMFullResponseEndFrame(), direction)
            return

        await self.push_frame(frame, direction)
