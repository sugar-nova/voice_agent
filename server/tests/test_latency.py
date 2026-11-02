"""Latency observer tests (M1-05–M1-07)."""

from __future__ import annotations

import json

from pipecat.frames.frames import (
    TextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import FramePushed
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from app.agents.echo import EchoProcessor, format_echo_response
from app.observers.latency import TurnLatencyTracker, emit_turn_log_line, turn_log_payload
from app.schemas import LatencyStages


class _StubProcessor(FrameProcessor):
    pass


def test_turn_log_payload_jq_friendly() -> None:
    tracker = TurnLatencyTracker(vad_silence_ms=450.0)
    tracker.begin_turn_at_t0(1.0)
    tracker.mark_t1(1.1)
    tracker.mark_t2(1.11)
    tracker.mark_t3(1.4)
    tracker.mark_t4(1.41)

    assert len(tracker.completed) == 1
    line = emit_turn_log_line(tracker.completed[0])
    data = json.loads(line)
    assert data["turnId"] == 1
    assert data["vad_silence_ms"] == 450.0
    assert data["stages"]["t0"] == 1.0
    assert data["stages"]["t4"] == 1.41


def test_tracker_records_all_five_stages_in_memory() -> None:
    vad_ms = 400.0
    tracker = TurnLatencyTracker(vad_silence_ms=vad_ms)
    echo = EchoProcessor()
    tts = _StubProcessor()
    output = _StubProcessor()
    sink = _StubProcessor()

    times = [0.0, 0.05, 0.06, 0.2, 0.21]
    idx = 0

    def ts() -> float:
        nonlocal idx
        value = times[idx]
        idx += 1
        return value

    tracker.handle_push(
        _push(VADUserStoppedSpeakingFrame(), _StubProcessor(), _StubProcessor()),
        timestamp=ts(),
    )
    tracker.handle_push(
        _push(
            TranscriptionFrame(text="hello", user_id="u", timestamp="t"),
            _StubProcessor(),
            echo,
        ),
        echo_processor=echo,
        timestamp=ts(),
    )
    tracker.handle_push(
        _push(TextFrame(text=format_echo_response("hello") or ""), echo, tts),
        echo_processor=echo,
        timestamp=ts(),
    )
    audio = TTSAudioRawFrame(audio=b"\x00\x00", sample_rate=16000, num_channels=1)
    tracker.handle_push(
        _push(audio, tts, output),
        echo_processor=echo,
        tts_processor=tts,
        output_processor=output,
        timestamp=ts(),
    )
    tracker.handle_push(
        _push(audio, output, sink),
        echo_processor=echo,
        tts_processor=tts,
        output_processor=output,
        timestamp=ts(),
    )

    assert len(tracker.completed) == 1
    stages = tracker.completed[0].stages
    assert isinstance(stages, LatencyStages)
    assert stages.t0 == 0.0
    assert stages.t1 == 0.05
    assert stages.t2 == 0.06
    assert stages.t3 == 0.2
    assert stages.t4 == 0.21
    assert tracker.completed[0].vad_silence_ms == vad_ms

    payload = turn_log_payload(tracker.completed[0])
    assert payload["event"] == "turn_latency"


def _push(
    frame,
    source: FrameProcessor,
    destination: FrameProcessor,
) -> FramePushed:
    return FramePushed(
        source=source,
        destination=destination,
        frame=frame,
        direction=FrameDirection.DOWNSTREAM,
        timestamp=0,
        first_push=True,
    )
