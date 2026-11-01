# Voice agent server

Python 3.11+ FastAPI app and Pipecat pipeline (Phase 1).

```bash
# from repo root
python -m venv .venv
source .venv/bin/activate
pip install -e server
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Docker

From repo root:

```bash
docker compose up --build
# or: docker build -f server/Dockerfile -t voice-agent-server .
```
