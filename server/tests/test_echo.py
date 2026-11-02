"""Tests for echo agent (M1-04)."""

from __future__ import annotations

import pytest
from pipecat.frames.frames import (
    InterimTranscriptionFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.processors.frame_processor import FrameDirection

from app.agents.echo import EchoProcessor, format_echo_response, is_final_transcription


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("hello", "I heard you say: hello"),
        ("  hello  ", "I heard you say: hello"),
        ("", None),
        ("   ", None),
        (
            "Supercalifragilisticexpialidocious " * 10,
            "I heard you say: " + ("Supercalifragilisticexpialidocious " * 10).strip(),
        ),
        (" café — naïve 123 ", "I heard you say: café — naïve 123"),
        ("Hello!!!", "I heard you say: Hello!!!"),
    ],
)
def test_format_echo_response(raw: str, expected: str | None) -> None:
    assert format_echo_response(raw) == expected


def test_is_final_transcription() -> None:
    assert is_final_transcription(
        TranscriptionFrame(text="hi", user_id="u", timestamp="t")
    )
    assert not is_final_transcription(
        InterimTranscriptionFrame(text="hi", user_id="u", timestamp="t")
    )


@pytest.mark.asyncio
async def test_echo_processor_ignores_empty_final() -> None:
    processor = EchoProcessor()
    pushed: list = []

    async def capture(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append(frame)

    processor.push_frame = capture  # type: ignore[method-assign]

    await processor.process_frame(
        TranscriptionFrame(text="   ", user_id="u", timestamp="t"),
        FrameDirection.DOWNSTREAM,
    )

    assert len(pushed) == 1
    assert isinstance(pushed[0], TranscriptionFrame)
    assert format_echo_response(pushed[0].text) is None


@pytest.mark.asyncio
async def test_echo_processor_passes_interim() -> None:
    processor = EchoProcessor()
    pushed: list = []

    async def capture(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append(frame)

    processor.push_frame = capture  # type: ignore[method-assign]

    interim = InterimTranscriptionFrame(text="hel", user_id="u", timestamp="t")
    await processor.process_frame(interim, FrameDirection.DOWNSTREAM)

    assert pushed == [interim]


@pytest.mark.asyncio
async def test_echo_processor_emits_agent_text_on_final() -> None:
    processor = EchoProcessor()
    pushed: list = []

    async def capture(frame, direction=FrameDirection.DOWNSTREAM):
        pushed.append(frame)

    processor.push_frame = capture  # type: ignore[method-assign]

    final = TranscriptionFrame(text="hello", user_id="u", timestamp="t")
    await processor.process_frame(final, FrameDirection.DOWNSTREAM)

    assert len(pushed) == 4
    assert pushed[0] is final
    assert isinstance(pushed[1], LLMFullResponseStartFrame)
    assert isinstance(pushed[3], LLMFullResponseEndFrame)
    agent_frames = [f for f in pushed if isinstance(f, TextFrame) and f is not final]
    assert len(agent_frames) == 1
    assert agent_frames[0].text == "I heard you say: hello"
