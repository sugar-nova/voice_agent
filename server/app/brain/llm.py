"""Layer 2 answer synthesis with a local Ollama model (M4B-11)."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Sequence
from typing import Protocol

import aiohttp

from app.brain.l2 import L2Chunk

NOT_COVERED = "NOT_COVERED"

SYSTEM_PROMPT = (
    "You help callers of a Wise voice assistant that ONLY handles the status of money transfers "
    "the caller sent with Wise: tracking, timing, processing delays, sent but not arrived, "
    "recipient not paid, receipts or proof of payment, transfer references, cancelled or failed "
    "transfers, and status emails. Everything else is out of scope: card payments, chargebacks, "
    "account verification, login, fees, exchange rates, creating transfers, money from other "
    "apps, incoming salary or deposits, business accounts. Answer ONLY using the FAQ context. "
    "Reply in one or two short spoken sentences. If the context does not answer the question or "
    f"it is out of scope, reply exactly {NOT_COVERED}."
)


class L2Synthesizer(Protocol):
    def stream(self, query: str, chunks: Sequence[L2Chunk]) -> AsyncGenerator[str, None]: ...


def build_user_prompt(query: str, chunks: Sequence[L2Chunk]) -> str:
    context = "\n".join(
        f"{i}. {chunk.question} -> {chunk.answer}" for i, chunk in enumerate(chunks, start=1)
    )
    return f"FAQ context:\n{context}\n\nCaller question: {query}"


class OllamaSynthesizer:
    def __init__(self, *, url: str, model: str, timeout_secs: float = 10.0) -> None:
        self._endpoint = f"{url.rstrip('/')}/api/chat"
        self._model = model
        self._timeout = aiohttp.ClientTimeout(total=timeout_secs)

    async def stream(self, query: str, chunks: Sequence[L2Chunk]) -> AsyncGenerator[str, None]:
        body = {
            "model": self._model,
            "stream": True,
            "keep_alive": "30m",
            "options": {"temperature": 0, "num_predict": 120},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(query, chunks)},
            ],
        }
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            async with session.post(self._endpoint, json=body) as response:
                response.raise_for_status()
                async for line in response.content:
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    token = data.get("message", {}).get("content", "")
                    if token:
                        yield token
                    if data.get("done"):
                        return
