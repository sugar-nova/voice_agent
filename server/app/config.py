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

    @classmethod
    def from_env(cls) -> Settings:
        env_file = _load_env()
        port_raw = os.getenv("PORT", "8000")
        return cls(
            env_file=env_file,
            deepgram_api_key=os.getenv("DEEPGRAM_API_KEY") or None,
            cartesia_api_key=os.getenv("CARTESIA_API_KEY") or None,
            cartesia_voice_id=os.getenv("CARTESIA_VOICE_ID") or None,
            port=int(port_raw),
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        )

    def log_summary(self) -> str:
        env_path = self.env_file if self.env_file else "(no .env file found)"
        return (
            f"config env_file={env_path} port={self.port} log_level={self.log_level} "
            f"DEEPGRAM_API_KEY={_redact(self.deepgram_api_key)} "
            f"CARTESIA_API_KEY={_redact(self.cartesia_api_key)} "
            f"CARTESIA_VOICE_ID={_redact(self.cartesia_voice_id)}"
        )
