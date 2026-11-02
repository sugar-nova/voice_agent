#!/usr/bin/env python3
"""M4B-05: populate Redis hash keys for FAQ vectors (see app.brain.redis_index)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "server"))

from app.brain.embeddings import FastEmbedder  # noqa: E402
from app.brain.redis_index import RedisL1Router  # noqa: E402
from app.config import Settings  # noqa: E402
from app.kb.load import load_faqs  # noqa: E402


def main() -> int:
    import redis

    settings = Settings.from_env()
    if not settings.redis_url:
        print("REDIS_URL is not set", file=sys.stderr)
        return 1
    client = redis.from_url(settings.redis_url, decode_responses=True)
    pong = client.ping()
    if not pong:
        print("Redis PING failed", file=sys.stderr)
        return 1
    modules = client.execute_command("MODULE", "LIST")
    module_names: list[str] = []
    for module in modules:
        if not isinstance(module, list):
            continue
        for i in range(len(module) - 1):
            key = module[i]
            value = module[i + 1]
            key_text = key.decode() if isinstance(key, bytes) else str(key)
            if key_text == "name":
                value_text = value.decode() if isinstance(value, bytes) else str(value)
                module_names.append(value_text)
                break
    if not any(name in ("search", "ft") for name in module_names):
        print("RediSearch module is missing. Start redis-stack-server.", file=sys.stderr)
        return 1

    entries = load_faqs()
    embedder = FastEmbedder(settings.embedding_model)
    router = RedisL1Router(
        entries=entries,
        embedder=embedder,
        redis_url=settings.redis_url,
        index_name=settings.redis_index_name,
    )
    sample = router.lookup("Where is my money?")
    index_info = client.execute_command("FT.INFO", settings.redis_index_name)
    print(f"ping={pong} redis_modules={','.join(module_names)}")
    print(
        f"index={settings.redis_index_name} rows={router.indexed_rows} "
        f"faq_entries={len(entries)} backend={sample.backend} similarity={sample.similarity:.4f}"
    )
    print(f"ft_info={index_info}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
