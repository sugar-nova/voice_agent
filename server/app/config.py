"""Environment-backed settings (M0-12)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Repo root: server/app/config.py -> server -> repo
REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_CANDIDATES = (REPO_ROOT / "config" / ".env", REPO_ROOT / ".env")


def _load_env() -> Path | None:
    for path in ENV_CANDIDATES:
        if path.is_file():
            load_dotenv(path)
            return path
    return None


def _redact(value: str | None) -> str:
    if not value:
        return "(not set)"
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}…{value[-4:]}"


@dataclass(frozen=True)
class Settings:
    env_file: Path | None
    deepgram_api_key: str | None
    cartesia_api_key: str | None
    cartesia_voice_id: str | None
    port: int
    log_level: str
    agent_mode: str
    brain_l1_threshold: float
    brain_enable_l2: bool
    brain_l2_relevance_floor: float
    embedding_provider: str
    embedding_model: str
    redis_url: str | None
    redis_index_name: str
    qdrant_url: str | None
    qdrant_collection: str
    ollama_url: str
    ollama_model: str

    @classmethod
    def from_env(cls) -> Settings:
        env_file = _load_env()
        port_raw = os.getenv("PORT", "8000")
        agent_mode = os.getenv("AGENT_MODE", "echo").strip().lower()
        if agent_mode not in ("echo", "brain"):
            agent_mode = "echo"
        return cls(
            env_file=env_file,
            deepgram_api_key=os.getenv("DEEPGRAM_API_KEY") or None,
            cartesia_api_key=os.getenv("CARTESIA_API_KEY") or None,
            cartesia_voice_id=os.getenv("CARTESIA_VOICE_ID") or None,
            port=int(port_raw),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            agent_mode=agent_mode,
            brain_l1_threshold=float(os.getenv("BRAIN_L1_THRESHOLD", "0.95")),
            brain_enable_l2=os.getenv("BRAIN_ENABLE_L2", "false").strip().lower()
            in ("1", "true", "yes"),
            brain_l2_relevance_floor=float(os.getenv("BRAIN_L2_RELEVANCE_FLOOR", "0.60")),
            embedding_provider=os.getenv("EMBEDDING_PROVIDER", "fastembed"),
            embedding_model=os.getenv(
                "EMBEDDING_MODEL",
                "BAAI/bge-small-en-v1.5",
            ),
            redis_url=os.getenv("REDIS_URL") or None,
            redis_index_name=os.getenv("REDIS_INDEX_NAME", "brain:faq"),
            qdrant_url=os.getenv("QDRANT_URL") or None,
            qdrant_collection=os.getenv("QDRANT_COLLECTION", "wise_where_is_money"),
            ollama_url=os.getenv("OLLAMA_URL", "http://127.0.0.1:11434"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen2.5:3b"),
        )

    def log_summary(self) -> str:
        env_path = self.env_file if self.env_file else "(no .env file found)"
        return (
            f"config env_file={env_path} port={self.port} log_level={self.log_level} "
            f"AGENT_MODE={self.agent_mode} BRAIN_ENABLE_L2={self.brain_enable_l2} "
            f"DEEPGRAM_API_KEY={_redact(self.deepgram_api_key)} "
            f"CARTESIA_API_KEY={_redact(self.cartesia_api_key)} "
            f"CARTESIA_VOICE_ID={_redact(self.cartesia_voice_id)}"
        )
