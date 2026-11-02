# Voice Agent

A browser voice client and a Python server. The browser streams microphone audio over a WebSocket. The server runs voice activity detection, speech-to-text, an agent, and text-to-speech, then streams audio back for playback. Each turn records per-stage latency.

Two agent modes:

- **echo** — speaks back what it heard. Use this to check the audio path.
- **brain** — answers a small Wise “where is my money” FAQ. A close match is read straight from a Redis vector index. With Layer 2 enabled, other questions go to Qdrant retrieval and a local Ollama model that may answer only from those FAQs. Anything else speaks a handoff line and the session closes.

## Architecture

```
Mic → AudioWorklet (PCM16, 16 kHz) → WebSocket
        → Silero VAD → Deepgram STT → agent → Cartesia TTS
        → WebSocket → playback worklet
```

The client is TypeScript and Vite. The server is Python 3.11, FastAPI, and [Pipecat](https://github.com/pipecat-ai/pipecat). Provider keys stay on the server.

## Requirements

- Python 3.11+
- Node.js 22+
- A [Deepgram](https://console.deepgram.com/) API key and a [Cartesia](https://play.cartesia.ai/) API key plus voice id
- Docker, only if you run the server or the vector stores in containers
- Redis Stack and Qdrant, only for the brain index. Ollama, only for Layer 2

## Quick start

From the repo root:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e "server[dev]"
cp config/.env.example config/.env
```

Put `DEEPGRAM_API_KEY`, `CARTESIA_API_KEY`, and `CARTESIA_VOICE_ID` in `config/.env`. That file stays local.

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```bash
cd client
npm install
npm run dev
```

Open the URL Vite prints, choose Connect, and allow the microphone. Vite proxies `/ws` to `http://127.0.0.1:8000`.

Health check: `curl http://127.0.0.1:8000/health`

### Docker

The compose file builds the server and starts Redis Stack and Qdrant. The browser client still runs on the host.

```bash
docker compose up --build
```

Compose reads `config/.env` or a root `.env` when either file exists.

### Brain mode

```bash
pip install -e "server[brain]"
```

Set `AGENT_MODE=brain` in `config/.env`. Leave `BRAIN_ENABLE_L2=false` to serve only the Redis index.

```bash
docker compose up redis qdrant -d
python scripts/build_redis_index.py
```

Layer 2 also needs a local model (`ollama pull qwen2.5:3b`), `BRAIN_ENABLE_L2=true`, and `QDRANT_URL=http://127.0.0.1:6333`.

Scope and content rules: [docs/kb-scope.md](docs/kb-scope.md).

### Provider smoke test

```bash
python scripts/generate_hello_fixture.py   # macOS; or see scripts/fixtures/README.md
python scripts/check_providers.py
```

## Configuration

Copy [config/.env.example](config/.env.example). The loader reads `config/.env`, then a root `.env`.

| Variable | Role |
|----------|------|
| `DEEPGRAM_API_KEY` | Streaming speech-to-text |
| `CARTESIA_API_KEY`, `CARTESIA_VOICE_ID` | Streaming speech synthesis |
| `AGENT_MODE` | `echo` or `brain` |
| `BRAIN_L1_THRESHOLD` | Minimum similarity for a direct FAQ hit |
| `BRAIN_ENABLE_L2` | Retrieval plus local LLM when Layer 1 misses |
| `REDIS_URL`, `QDRANT_URL`, `OLLAMA_URL` | Optional brain infrastructure |

## Tests

```bash
cd server && pytest
cd client && npm test
```

Server tests expect the install from `server/` so `pyproject.toml` configures pytest-asyncio. `pip install -e "server[dev,brain]"` also runs the Qdrant tests; without that extra they are skipped.

## Layout

| Path | Role |
|------|------|
| `client/` | Mic, playback, WebSocket transport, debug UI |
| `server/app/` | FastAPI app, Pipecat pipeline, agents, brain, FAQ data |
| `server/tests/` | Server tests |
| `config/` | Environment template |
| `scripts/` | Provider check, latency benches, index build, eval |
| `docs/` | Architecture notes and the latency log |

## Docs

| Doc | Contents |
|-----|----------|
| [docs/phase1-plan.md](docs/phase1-plan.md) | Pipeline, milestones, latency targets |
| [docs/phase1-implementation-steps.md](docs/phase1-implementation-steps.md) | Build checklist |
| [docs/directory-structure.md](docs/directory-structure.md) | Directory map |
| [docs/latency-log.md](docs/latency-log.md) | Measured timings |
| [docs/kb-scope.md](docs/kb-scope.md) | FAQ scope for brain mode |

Coding guidelines for changes in this repo: [CLAUDE.md](CLAUDE.md). Cursor applies the same text from `.cursor/rules/`.

## License

Reuse terms are unset. Add a `LICENSE` file before treating this repository as open source.
