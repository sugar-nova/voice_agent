# Voice Agent

Phase 1 proves the real-time browser–server audio pipeline (mic → STT → echo → TTS → speaker) with per-stage latency measurement before any business logic.

**Start here:** [docs/phase1-implementation-steps.md](docs/phase1-implementation-steps.md) — ordered micro-steps with “done when” checks.

| Doc | Purpose |
|-----|---------|
| [docs/phase1-plan.md](docs/phase1-plan.md) | Architecture, milestones, success criteria |
| [docs/directory-structure.md](docs/directory-structure.md) | Repo layout |
| [docs/latency-log.md](docs/latency-log.md) | Measurement notes per milestone |

Agent/coding guidelines: [CLAUDE.md](CLAUDE.md), [CURSOR.md](CURSOR.md).

## Docker (server)

From the repo root (optional `.env` for API keys once M0-11+ is done):

```bash
docker compose up --build
curl http://localhost:8000/health
```

Build or run the image alone:

```bash
docker build -f server/Dockerfile -t voice-agent-server .
docker run --rm -p 8000:8000 voice-agent-server
```

The Vite client still runs on the host with `cd client && npm run dev` until we add a client container.

## Provider smoke test (M0-14+)

```bash
cp config/.env.example .env   # add API keys locally
python scripts/generate_hello_fixture.py   # if hello.wav missing (macOS `say`)
python scripts/check_providers.py
```

Fill baseline numbers in [docs/latency-log.md](docs/latency-log.md).
