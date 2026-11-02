# Directory structure

```
[Browser Mic] ──PCM──> [WebSocket] ──> [Server: VAD → STT → Agent → TTS] ──> [WebSocket] ──> [Playback]
```

Speech-to-text and speech synthesis run on the server. Provider choice is configured with environment variables and `server/app/pipeline.py`.

## Top level

| Path | Role |
|------|------|
| `client/` | Browser mic, playback, transport, and debug UI |
| `server/` | FastAPI app, Pipecat pipeline, agents, brain, tests |
| `config/` | `config/.env.example` (copy to `config/.env`; never commit the copy) |
| `scripts/` | Provider smoke test, latency benches, Redis index build, brain evals |
| `docs/` | Architecture notes, FAQ scope, latency log |

## `client/`

| Path | Role |
|------|------|
| `public/worklets/` | AudioWorklet processors for capture and playback |
| `src/audio/` | Microphone, PCM framing, capture, playback buffer |
| `src/transport/` | WebSocket transport and message types |
| `src/main.ts` | Session controls, transcript, and latency panel |
| `vite.config.ts` | Dev server; proxies `/ws` to the API on port 8000 |

## `server/`

| Path | Role |
|------|------|
| `app/main.py` | FastAPI app and `/ws` session entry |
| `app/pipeline.py` | Pipecat pipeline: VAD, Deepgram, agent, Cartesia |
| `app/agents/` | `echo` (repeat the transcript) and `knowledge` (FAQ brain) |
| `app/brain/` | Embeddings, Redis Layer 1, Qdrant Layer 2, local LLM |
| `app/kb/` | FAQ YAML and eval queries |
| `app/observers/` | Per-turn latency log |
| `tests/` | Pytest suite (`cd server && pytest`) |

## Providers

STT and TTS are Pipecat services constructed in `app/pipeline.py`. Swapping a vendor is a server change; the browser transport stays the same. The default is Deepgram for STT and Cartesia for TTS. Agent logic stays in `app/agents/`, so echo and the FAQ brain can change without touching audio capture.
