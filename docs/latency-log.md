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
| 2026-11-01 | macOS dev laptop; providers reached over a home/office network | 2702 | **1656** | **220** | `check_providers.py`; fixture `hello.wav`. Final transcript: `Hello.` (partial vs full phrase). First interim arrived after final—use **1656 ms** as STT baseline. Cartesia total download 472 ms, 53 498 audio bytes. |
| 2026-11-01 | macOS dev laptop; providers reached over a home/office network | (none) | **3449** | n/a (STT-only run) | Re-ran after STT cut-off fix in `check_providers.py`; final transcript now: `What are your opening hours?`. Also reported `time_to_first_final_ms=1834.9`. |
| 2026-11-02 | macOS dev laptop | — | — | — | Playback of dummy audio succeeded. |

## Milestone 1 — Server bench (`bench_latency.py`)

| Date | Utterance | t0 | t1 | t2 | t3 | t4 | Notes |
|------|-----------|----|----|----|----|----|-------|
| | | | | | | | |

## Milestone 3+ — End-to-end (browser)

| Date | p50 perceived ms | p95 perceived ms | RTT ms | VAD silence ms | Playback buffer ms | Notes |
|------|------------------|------------------|--------|----------------|---------------------|-------|
| | | | | | | |

## Milestone 4B — Brain / DB query baselines (`bench_brain_queries.py`)

Isolated from STT/TTS/pipeline. Same embedding model and indexes as production.

| Date | Index entries | Embed p50/p95 ms | Redis KNN p50/p95 ms | Qdrant search p50/p95 ms | Stack (docker/host) | Notes |
|------|---------------|------------------|----------------------|---------------------------|---------------------|-------|
| 2026-11-02 | pending-run | pending-run | pending-run | n/a (L1-only) | local docker | Run `python scripts/bench_brain_queries.py --iterations 30 --warmup 5` with `AGENT_MODE=brain`, `BRAIN_ENABLE_L2=false`. |
| | | | | | | |

## Milestone 4B+ — Per-turn brain metrics (E2E, `agent=brain`)

Aggregated from JSON log / WS `metrics.brain` over N turns.

| Date | Route | N | embed p50/p95 | redis_knn p50/p95 | qdrant p50/p95 | llm_ttft p50/p95 | brain_ms p50/p95 | Notes |
|------|-------|---|---------------|-------------------|----------------|------------------|------------------|-------|
| | l1_hit | | | | n/a | n/a | | |
| | l2_rag | | | | | | | |
| | deflect | | | | | | | |

## Milestone 4B L1 E2E verification (`BRAIN_ENABLE_L2=false`)

| Date | In-scope paraphrase heard | Deflect handoff heard | WS closed after deflect | Route seen (`l1_hit` / `deflect`) | Notes |
|------|---------------------------|------------------------|--------------------------|------------------------------------|-------|
| | | | | | |

## Tuning passes (M5)

| Change | Before p50 | After p50 | Before p95 | After p95 | Notes |
|--------|------------|-----------|------------|-----------|-------|
| | | | | | |
