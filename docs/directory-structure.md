# Directory structure (Phase 1 — Echo agent)

Pipeline this layout supports:

```
[Browser Mic] ──PCM──> [Transport] ──> [Server: VAD → STT → Agent → TTS] ──> [Transport] ──> [Playback]
```

STT and TTS run on the **server** (Pipecat pipeline). Provider choice (Deepgram first, others later) is configured in server settings and `pipeline.py`, not under `client/`.

**Spec:** [phase1-plan.md §5](./phase1-plan.md#5-repository-structure)

## Top level

| Path | Role |
|------|------|
| `client/` | Browser: mic/speaker worklets, transport, UI, client-side latency |
| `server/` | FastAPI + Pipecat pipeline, agents, observers, tests |
| `config/` | Environment templates and non-secret configuration |
| `scripts/` | Provider checks, latency benches, dev helpers |
| `docs/` | Architecture, phase plan, latency log |

## `client/`

| Path | Role |
|------|------|
| `public/worklets/` | AudioWorklet processors (capture → PCM16, playback jitter buffer) |
| `src/audio/` | Mic setup, `AudioContext`, worklet loading |
| `src/transport/` | Transport interface; WebSocket (later WebRTC) |
| `src/agent/` | Session orchestration (connect, state machine) |
| `src/metrics/` | Client-side timing (e.g. first frame played) |
| `src/ui/` | Controls, transcript, latency panel |

## `server/`

| Path | Role |
|------|------|
| `app/` | FastAPI entry, pipeline assembly, config, schemas |
| `app/agents/` | Turn logic (Phase 1: echo; later FAQ/search) |
| `app/observers/` | Pipeline observers (e.g. per-turn latency JSON) |
| `tests/` | Server unit/integration tests |

## Modular voice providers

- **STT / TTS** are wired in `app/pipeline.py` via Pipecat service classes. Swap providers by changing factory/config (env + small adapter module), without touching client transport or agent UI.
- **Phase 1 default:** Deepgram (STT) and Cartesia (TTS) per [phase1-plan.md](./phase1-plan.md).
- **Agent logic** stays in `app/agents/` so echo can be replaced independently of STT/TTS vendors.

## Removed (obsolete placeholders)

- `core/` — agent logic lives under `server/app/agents/`
- `server/src/` — replaced by `server/app/`
- `client/src/speech/` — browser no longer hosts STT/TTS adapters in Phase 1
- Root `tests/` — server tests live under `server/tests/` (client tests added with Vitest in later milestones)
