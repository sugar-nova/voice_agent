# Phase 1 latency log

Record measurements here as you complete milestones. One section per milestone or tuning pass.

## Baseline — Milestone 0 (provider smoke)

**Endpoints (from this repo):**

| Provider | Mode | URL |
|----------|------|-----|
| Deepgram | Streaming STT | `wss://api.deepgram.com/v1/listen` |
| Cartesia | TTS bytes | `https://api.cartesia.ai/tts/bytes` (API version header `2026-03-01`) |

**Your environment:** note machine / cloud region and date when you run the smoke script (closest region to those endpoints reduces RTT).

```bash
cp config/.env.example .env   # add keys
python scripts/check_providers.py
```

| Date | Machine / region | STT first interim ms | STT final ms | TTS TTFA ms | Notes |
|------|------------------|----------------------|--------------|-------------|-------|
| | | | | | |

## Milestone 1 — Server bench (`bench_latency.py`)

| Date | Utterance | t0 | t1 | t2 | t3 | t4 | Notes |
|------|-----------|----|----|----|----|----|-------|
| | | | | | | | |

## Milestone 3+ — End-to-end (browser)

| Date | p50 perceived ms | p95 perceived ms | RTT ms | VAD silence ms | Playback buffer ms | Notes |
|------|------------------|------------------|--------|----------------|---------------------|-------|
| | | | | | | |

## Tuning passes (M5)

| Change | Before p50 | After p50 | Before p95 | After p95 | Notes |
|--------|------------|-----------|------------|-----------|-------|
| | | | | | |
