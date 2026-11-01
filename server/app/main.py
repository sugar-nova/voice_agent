"""FastAPI entrypoint."""

import logging

from fastapi import FastAPI

from app.config import Settings

app = FastAPI(title="voice-agent-server")


@app.on_event("startup")
def log_config() -> None:
    settings = Settings.from_env()
    logging.getLogger("voice_agent.config").info(settings.log_summary())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
