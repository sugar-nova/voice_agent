# Voice agent server

Python 3.11+ FastAPI app and Pipecat pipeline. Setup for the whole repo, including the browser client, is in the [root README](../README.md).

From this directory, after `pip install -e ".[dev]"` from the repo root (or `pip install -e ".[dev]"` here):

```bash
pytest
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`app` is the installed package, so uvicorn can run from the repo root as well.

Docker, from the repo root:

```bash
docker compose up --build
```
