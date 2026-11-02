#!/usr/bin/env python3
"""M4B-03: smoke-test embedding provider and print vector dimension."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "server"))

from app.brain.embeddings import FastEmbedder  # noqa: E402
from app.config import Settings  # noqa: E402


def main() -> int:
    settings = Settings.from_env()
    embedder = FastEmbedder(settings.embedding_model)
    vector = embedder.embed(["Where is my money?"])[0]
    print(f"provider={settings.embedding_provider} model={settings.embedding_model}")
    print(f"dimension={embedder.dimension} sample_len={len(vector)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
