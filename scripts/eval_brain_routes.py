#!/usr/bin/env python3
"""End-to-end routing eval (L1 -> L2 Qdrant + local LLM -> deflect) over fixture YAMLs.

Runs the real BrainService from config/.env. In-scope fixtures should be answered
(l1_hit or l2_rag); out-of-scope fixtures should deflect.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import statistics
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "server"))

from app.brain.decision import build_brain_service  # noqa: E402
from app.config import Settings  # noqa: E402

KB_DIR = REPO_ROOT / "server" / "app" / "kb"
DEFAULT_EVAL_FILES = [KB_DIR / "eval_queries.yaml", KB_DIR / "eval_queries_hard_negatives.yaml"]


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-file", type=Path, action="append", help="Fixture YAML (repeatable)")
    parser.add_argument("--l1-threshold", type=float, help="Override BRAIN_L1_THRESHOLD")
    parser.add_argument("--no-l2", action="store_true", help="Evaluate L1 only")
    args = parser.parse_args()

    settings = Settings.from_env()
    overrides: dict[str, object] = {"brain_enable_l2": not args.no_l2}
    if args.l1_threshold is not None:
        overrides["brain_l1_threshold"] = args.l1_threshold
    settings = dataclasses.replace(settings, **overrides)

    fixtures = []
    for path in args.eval_file or DEFAULT_EVAL_FILES:
        fixtures += yaml.safe_load(path.read_text(encoding="utf-8"))

    brain = build_brain_service(settings)
    l1_backend = type(brain._l1).__name__
    l2_backend = getattr(brain._l2, "backend", "off")
    print(
        f"L1={l1_backend} threshold={settings.brain_l1_threshold:.2f} | "
        f"L2={l2_backend} floor={settings.brain_l2_relevance_floor:.2f} "
        f"model={settings.ollama_model if settings.brain_enable_l2 else 'off'}"
    )
    if brain._llm is not None:
        async for _ in brain._llm.stream("hi", []):
            pass

    answered_ok = wrong_faq = oos_answered = in_deflected = 0
    l2_first_token: list[float] = []
    for item in fixtures:
        text, in_scope = item["text"], bool(item["in_scope"])
        expected = item.get("expected_faq_id")
        decision = await brain.decide(text)
        answer = decision.answer_text
        if decision.answer_stream is not None:
            answer += "".join([token async for token in decision.answer_stream])
            l2_first_token.append(decision.metrics.llm_first_token_ms or 0.0)

        answered = decision.route != "deflect"
        if in_scope and not answered:
            verdict, in_deflected = "IN-SCOPE DEFLECTED", in_deflected + 1
        elif not in_scope and answered:
            verdict, oos_answered = "OUT-OF-SCOPE ANSWERED", oos_answered + 1
        elif in_scope and decision.route == "l1_hit" and expected and decision.faq_id != expected:
            verdict, wrong_faq = f"WRONG FAQ ({decision.faq_id})", wrong_faq + 1
        else:
            verdict = "ok"
            answered_ok += in_scope

        sim = decision.metrics.redis_similarity or 0.0
        shown = answer.replace("\n", " ")[:90] if answered else ""
        print(
            f"{'IN ' if in_scope else 'OUT'} {decision.route:7s} L1={sim:.3f} {verdict:22s} "
            f"{text}  {('-> ' + shown) if shown else ''}"
        )

    n_in = sum(1 for f in fixtures if f["in_scope"])
    print()
    print(
        f"in-scope answered={answered_ok}/{n_in} wrong_faq={wrong_faq} deflected={in_deflected} | "
        f"out-of-scope answered={oos_answered}/{len(fixtures) - n_in}"
    )
    if l2_first_token:
        print(
            f"l2 turns={len(l2_first_token)} llm_first_token_ms "
            f"p50={statistics.median(l2_first_token):.0f} max={max(l2_first_token):.0f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
