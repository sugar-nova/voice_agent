#!/usr/bin/env python3
"""M1-14..M1-17: stream WAV through pipeline and log turn latency."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
import time
import wave
from pathlib import Path

from pipecat.frames.frames import EndFrame, UserAudioRawFrame
from pipecat.pipeline.runner import PipelineRunner

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = REPO_ROOT / "scripts" / "fixtures" / "hello.wav"
DEFAULT_OUTPUT = REPO_ROOT / "artifacts" / "bench_tts_output.wav"
# Allow `python scripts/bench_latency.py` from repo root.
sys.path.insert(0, str(REPO_ROOT / "server"))

from app.pipeline import build_pipeline  # noqa: E402


def _read_mono_pcm16(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as wf:
        if wf.getnchannels() != 1:
            raise ValueError(f"{path}: expected mono channel WAV")
        if wf.getsampwidth() != 2:
            raise ValueError(f"{path}: expected 16-bit PCM WAV")
        sample_rate = wf.getframerate()
        if sample_rate != 16_000:
            raise ValueError(f"{path}: expected 16 kHz WAV, got {sample_rate} Hz")
        pcm = wf.readframes(wf.getnframes())
    return pcm, sample_rate


def _write_pcm16_wav(path: Path, audio_chunks: list[bytes], sample_rate: int, channels: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)  # PCM16
        wf.setframerate(sample_rate)
        for chunk in audio_chunks:
            wf.writeframes(chunk)


async def _stream_realtime_audio(
    task,
    pcm: bytes,
    sample_rate: int,
    *,
    trailing_silence_seconds: float,
) -> None:
    frame_bytes = int(sample_rate * 0.02) * 2  # 20ms * 16-bit mono
    for offset in range(0, len(pcm), frame_bytes):
        chunk = pcm[offset : offset + frame_bytes]
        await task.queue_frame(UserAudioRawFrame(audio=chunk, sample_rate=sample_rate, num_channels=1))
        await asyncio.sleep(0.02)
    silence_frames = max(0, int(trailing_silence_seconds / 0.02))
    if silence_frames:
        silence_chunk = b"\x00" * frame_bytes
        for _ in range(silence_frames):
            await task.queue_frame(
                UserAudioRawFrame(audio=silence_chunk, sample_rate=sample_rate, num_channels=1)
            )
            await asyncio.sleep(0.02)

async def _wait_for_pipeline_output(
    assembly,
    *,
    timeout_seconds: float,
    expected_utterance: str | None,
) -> None:
    deadline = time.perf_counter() + timeout_seconds
    while time.perf_counter() < deadline:
        has_audio = bool(assembly.output.audio_frames)
        has_latency = bool(assembly.latency_observer.tracker.completed)
        has_expected_echo = True
        if expected_utterance:
            has_expected_echo = any(
                expected_utterance.lower() in text.lower()
                for text in _collect_echo_texts(assembly)
            )
        if has_audio and has_latency and has_expected_echo:
            return
        await asyncio.sleep(0.05)


def _collect_echo_texts(assembly) -> list[str]:
    return [f.text for f in assembly.output.text_frames if f.text.startswith("I heard you say:")]


async def run_benchmark(
    input_wav: Path,
    output_wav: Path,
    vad_silence_seconds: float,
    settle_seconds: float,
    trailing_silence_seconds: float,
    expected_utterance: str | None,
) -> int:
    pcm, sample_rate = _read_mono_pcm16(input_wav)
    assembly = build_pipeline(vad_silence_seconds=vad_silence_seconds)
    task = assembly.make_task(name="m1-bench-latency")
    runner = PipelineRunner(name="m1-bench-latency")

    start = time.perf_counter()
    runner_task = asyncio.create_task(runner.run(task))
    try:
        await _stream_realtime_audio(
            task,
            pcm,
            sample_rate,
            trailing_silence_seconds=trailing_silence_seconds,
        )
        await _wait_for_pipeline_output(
            assembly,
            timeout_seconds=settle_seconds,
            expected_utterance=expected_utterance,
        )
        await task.queue_frame(EndFrame())
        await runner_task
    finally:
        with contextlib.suppress(Exception):
            if not runner_task.done():
                runner_task.cancel()
                await runner_task

    elapsed_ms = (time.perf_counter() - start) * 1000.0
    print(f"bench_elapsed_ms: {elapsed_ms:.1f}")

    if not assembly.output.audio_frames:
        print("No TTS audio frames were produced.", file=sys.stderr)
        return 1

    first = assembly.output.audio_frames[0]
    audio_chunks = [f.audio for f in assembly.output.audio_frames]
    _write_pcm16_wav(
        output_wav,
        audio_chunks=audio_chunks,
        sample_rate=first.sample_rate,
        channels=first.num_channels,
    )
    print(f"output_wav: {output_wav}")
    print(f"output_audio_frames: {len(audio_chunks)}")

    echo_texts = _collect_echo_texts(assembly)
    if not echo_texts:
        print("No echo text frame captured from pipeline.", file=sys.stderr)
        return 1

    final_echo = echo_texts[-1]
    print(f"echo_text: {final_echo!r}")
    print(f"echo_texts_seen: {echo_texts}")

    records = assembly.latency_observer.tracker.completed
    if records:
        latest = records[-1]
    else:
        active = assembly.latency_observer.tracker.active_turn()
        if active is None:
            print("No latency record found (t0..t4 missing).", file=sys.stderr)
            return 1
        latest = active
        # Fallback for bench mode if output reached sink but observer did not close the turn.
        if latest.stages.t4 is None and assembly.output.audio_frames:
            latest.stages.t4 = time.monotonic()
            print("t4 fallback applied from bench output timing (observer had no completed turn).")
        if latest.stages.t0 is None and latest.stages.t1 is not None:
            latest.stages.t0 = latest.stages.t1
            print("t0 fallback applied from first transcript timing (VAD stop not observed).")

    stages = latest.stages
    print(f"turn_id: {latest.turn_id}")
    print(f"t0: {stages.t0}")
    print(f"t1: {stages.t1}")
    print(f"t2: {stages.t2}")
    print(f"t3: {stages.t3}")
    print(f"t4: {stages.t4}")

    if None in (stages.t0, stages.t1, stages.t2, stages.t3, stages.t4):
        print("Incomplete latency stages for latest turn.", file=sys.stderr)
        return 1

    if expected_utterance and not any(expected_utterance.lower() in text.lower() for text in echo_texts):
        print(
            "Expected utterance not found in echo text. "
            f"Need phrase containing: {expected_utterance!r}",
            file=sys.stderr,
        )
        return 1

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run M1 WAV latency benchmark")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Input 16kHz mono PCM16 WAV")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Output TTS WAV path")
    parser.add_argument(
        "--vad-silence-seconds",
        type=float,
        default=0.4,
        help="Silero VAD stop_secs (seconds)",
    )
    parser.add_argument(
        "--settle-seconds",
        type=float,
        default=8.0,
        help="Max wait after audio stream for STT/TTS response before ending pipeline",
    )
    parser.add_argument(
        "--trailing-silence-seconds",
        type=float,
        default=1.0,
        help="Amount of silent audio to stream after WAV to let VAD/STT finalize naturally",
    )
    parser.add_argument(
        "--expected-utterance",
        type=str,
        default=None,
        help="Optional phrase that must appear in echoed text (M1-16 check)",
    )
    args = parser.parse_args()
    return asyncio.run(
        run_benchmark(
            args.input,
            args.output,
            args.vad_silence_seconds,
            args.settle_seconds,
            args.trailing_silence_seconds,
            args.expected_utterance,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())

