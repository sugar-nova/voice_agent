#!/usr/bin/env python3
"""M0-15 / M0-16: smoke-test Deepgram STT and Cartesia TTS latency from local .env."""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
import wave
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = REPO_ROOT / "scripts" / "fixtures" / "hello.wav"
CARTESIA_API_VERSION = "2026-03-01"
CARTESIA_BYTES_URL = "https://api.cartesia.ai/tts/bytes"

# Ensure `app.config` is importable when run as `python scripts/check_providers.py`
sys.path.insert(0, str(REPO_ROOT / "server"))

from app.config import Settings  # noqa: E402


def _read_pcm16_mono(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as wf:
        if wf.getnchannels() != 1:
            raise ValueError(f"{path}: expected mono audio")
        if wf.getsampwidth() != 2:
            raise ValueError(f"{path}: expected 16-bit PCM")
        rate = wf.getframerate()
        pcm = wf.readframes(wf.getnframes())
    return pcm, rate


async def check_deepgram(settings: Settings) -> int:
    if not settings.deepgram_api_key:
        print("DEEPGRAM_API_KEY missing — set it in .env (see config/.env.example)", file=sys.stderr)
        return 1
    if not FIXTURE.is_file():
        print(f"Fixture missing: {FIXTURE}\nRun: python scripts/generate_hello_fixture.py", file=sys.stderr)
        return 1

    from deepgram import AsyncDeepgramClient
    from deepgram.listen.v1.types import ListenV1Results

    pcm, sample_rate = _read_pcm16_mono(FIXTURE)
    client = AsyncDeepgramClient(api_key=settings.deepgram_api_key)

    t0 = time.perf_counter()
    first_interim_ms: float | None = None
    first_final_ms: float | None = None
    last_final_ms: float | None = None
    final_transcript = ""
    stream_closed = asyncio.Event()
    receive_error: Exception | None = None

    async def receive_loop(connection) -> None:
        nonlocal first_interim_ms, first_final_ms, last_final_ms, final_transcript, receive_error
        try:
            async for message in connection:
                if not isinstance(message, ListenV1Results):
                    continue
                channel = message.channel
                if not channel or not channel.alternatives:
                    continue
                text = (channel.alternatives[0].transcript or "").strip()
                if not text:
                    continue
                elapsed_ms = (time.perf_counter() - t0) * 1000
                if message.is_final:
                    if first_final_ms is None:
                        first_final_ms = elapsed_ms
                    last_final_ms = elapsed_ms
                    # Keep the most complete text if service emits multiple finals.
                    if len(text) >= len(final_transcript):
                        final_transcript = text
                elif first_interim_ms is None and first_final_ms is None:
                    # Ignore interim chunks that arrive after the first final.
                    first_interim_ms = elapsed_ms
        except Exception as exc:  # websocket close path can raise after finalize
            receive_error = exc
        finally:
            stream_closed.set()

    print(f"Deepgram STT (streaming) fixture={FIXTURE.name} sample_rate={sample_rate}")
    async with client.listen.v1.connect(
        model="nova-3",
        encoding="linear16",
        sample_rate=str(sample_rate),
        interim_results="true",
        smart_format="true",
        punctuate="true",
    ) as connection:
        receiver = asyncio.create_task(receive_loop(connection))
        chunk_bytes = int(sample_rate * 0.02) * 2  # 20 ms frames
        for offset in range(0, len(pcm), chunk_bytes):
            await connection.send_media(pcm[offset : offset + chunk_bytes])
            await asyncio.sleep(0.02)
        await connection.send_finalize()
        try:
            await asyncio.wait_for(stream_closed.wait(), timeout=30.0)
        except TimeoutError:
            print("Timed out waiting for Deepgram stream close", file=sys.stderr)
            receiver.cancel()
            return 1

    print(f"  transcript (final): {final_transcript!r}")
    if first_interim_ms is not None:
        print(f"  time_to_first_interim_ms: {first_interim_ms:.1f}")
    else:
        print("  time_to_first_interim_ms: (none)")
    if first_final_ms is not None:
        print(f"  time_to_first_final_ms: {first_final_ms:.1f}")
    if last_final_ms is not None:
        print(f"  time_to_final_ms: {last_final_ms:.1f}")
    if receive_error and not final_transcript:
        print(f"Deepgram stream error: {receive_error}", file=sys.stderr)
        return 1
    if not final_transcript:
        print("No final Deepgram transcript received", file=sys.stderr)
        return 1
    return 0


def check_cartesia(settings: Settings) -> int:
    if not settings.cartesia_api_key or not settings.cartesia_voice_id:
        print(
            "CARTESIA_API_KEY and CARTESIA_VOICE_ID required — set in .env",
            file=sys.stderr,
        )
        return 1

    sentence = "Phase one provider check."
    payload = {
        "model_id": "sonic-3",
        "transcript": sentence,
        "voice": {"mode": "id", "id": settings.cartesia_voice_id},
        "output_format": {
            "container": "raw",
            "encoding": "pcm_s16le",
            "sample_rate": 16000,
        },
    }
    headers = {
        "X-API-Key": settings.cartesia_api_key,
        "Cartesia-Version": CARTESIA_API_VERSION,
        "Content-Type": "application/json",
    }

    print(f"Cartesia TTS (bytes) url={CARTESIA_BYTES_URL}")
    print(f"  text: {sentence!r}")

    t0 = time.perf_counter()
    ttfa_ms: float | None = None
    total_bytes = 0

    with httpx.Client(timeout=60.0) as client:
        with client.stream("POST", CARTESIA_BYTES_URL, headers=headers, json=payload) as response:
            if response.status_code != 200:
                body = response.read().decode(errors="replace")
                print(f"Cartesia error {response.status_code}: {body}", file=sys.stderr)
                return 1
            for chunk in response.iter_bytes(1024):
                if chunk and ttfa_ms is None:
                    ttfa_ms = (time.perf_counter() - t0) * 1000
                total_bytes += len(chunk)

    total_ms = (time.perf_counter() - t0) * 1000
    print(f"  time_to_first_audio_byte_ms: {ttfa_ms:.1f}" if ttfa_ms else "  time_to_first_audio_byte_ms: (none)")
    print(f"  total_download_ms: {total_ms:.1f}")
    print(f"  audio_bytes: {total_bytes}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Provider smoke tests (M0-15 / M0-16)")
    parser.add_argument(
        "--stt-only",
        action="store_true",
        help="Deepgram only",
    )
    parser.add_argument(
        "--tts-only",
        action="store_true",
        help="Cartesia only",
    )
    args = parser.parse_args()
    run_stt = not args.tts_only
    run_tts = not args.stt_only
    if args.stt_only and args.tts_only:
        print("Choose at most one of --stt-only / --tts-only", file=sys.stderr)
        return 1

    settings = Settings.from_env()
    exit_code = 0
    if run_stt:
        exit_code = asyncio.run(check_deepgram(settings)) or exit_code
    if run_tts:
        exit_code = check_cartesia(settings) or exit_code
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
