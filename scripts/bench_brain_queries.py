#!/usr/bin/env python3
"""M4B-22: offline brain routing latency baseline (no STT/TTS)."""

from __future__ import annotations

import argparse
import asyncio
import math
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "server"))

from app.brain.decision import build_brain_service  # noqa: E402
from app.config import Settings  # noqa: E402

FIXTURES = [
    ("Where is my money?", "l1_hit"),
    ("How can I see my transfer status?", "l1_hit"),
    ("Why is my transfer still processing?", "l1_hit"),
    ("Can I get a transfer receipt as proof of payment?", "l1_hit"),
    ("What are your opening hours?", "deflect"),
    ("How do I reset my password?", "deflect"),
]


def _p50(values: list[float]) -> float:
    return statistics.median(values)


def _p95(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    rank = max(0, min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1))
    return ordered[rank]


def _fmt_pair(values: list[float]) -> str:
    if not values:
        return "n/a"
    return f"{_p50(values):.2f}/{_p95(values):.2f}"


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--iterations",
        type=int,
        default=30,
        help="Measured iterations over the full fixture set (default: 30)",
    )
    parser.add_argument(
        "--warmup",
        type=int,
        default=5,
        help="Warmup iterations over the full fixture set (default: 5)",
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    if settings.agent_mode != "brain":
        print("Set AGENT_MODE=brain for this bench", file=sys.stderr)
        return 1
    if settings.brain_enable_l2:
        print("Set BRAIN_ENABLE_L2=false for L1-only M4B-22 baseline", file=sys.stderr)
        return 1

    brain = build_brain_service(settings)
    if args.iterations <= 0:
        print("--iterations must be > 0", file=sys.stderr)
        return 1
    if args.warmup < 0:
        print("--warmup must be >= 0", file=sys.stderr)
        return 1

    for _ in range(args.warmup):
        for text, _expected_route in FIXTURES:
            await brain.decide(text)

    embed_samples: list[float] = []
    knn_samples: list[float] = []
    brain_samples: list[float] = []
    route_counts: dict[str, int] = defaultdict(int)
    embed_by_route: dict[str, list[float]] = defaultdict(list)
    knn_by_route: dict[str, list[float]] = defaultdict(list)
    brain_by_route: dict[str, list[float]] = defaultdict(list)

    for _ in range(args.iterations):
        for text, expected_route in FIXTURES:
            t0 = time.perf_counter()
            decision = await brain.decide(text)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            route = decision.route
            route_counts[route] += 1

            embed_samples.append(decision.metrics.embed_ms)
            knn_samples.append(decision.metrics.redis_knn_ms)
            brain_samples.append(elapsed_ms)

            embed_by_route[route].append(decision.metrics.embed_ms)
            knn_by_route[route].append(decision.metrics.redis_knn_ms)
            brain_by_route[route].append(elapsed_ms)

            mismatch = " !!route_mismatch!!" if route != expected_route else ""
            print(
                f"{text!r} -> route={route} sim={decision.metrics.redis_similarity} "
                f"embed_ms={decision.metrics.embed_ms:.2f} "
                f"redis_knn_ms={decision.metrics.redis_knn_ms:.2f} "
                f"brain_ms={elapsed_ms:.2f}{mismatch}"
            )

    rows = getattr(getattr(brain, "_l1", object()), "indexed_rows", None)
    indexed_rows = str(rows) if isinstance(rows, int) else "unknown"

    print()
    print(
        f"summary iterations={args.iterations} warmup={args.warmup} "
        f"fixtures={len(FIXTURES)} indexed_rows={indexed_rows}"
    )
    print(
        f"overall embed_ms p50/p95={_fmt_pair(embed_samples)} "
        f"redis_knn_ms p50/p95={_fmt_pair(knn_samples)} "
        f"brain_ms p50/p95={_fmt_pair(brain_samples)}"
    )

    for route in sorted(route_counts.keys()):
        print(
            f"route={route} n={route_counts[route]} "
            f"embed_ms p50/p95={_fmt_pair(embed_by_route[route])} "
            f"redis_knn_ms p50/p95={_fmt_pair(knn_by_route[route])} "
            f"brain_ms p50/p95={_fmt_pair(brain_by_route[route])}"
        )

    print()
    print(
        "latency_log_row_template "
        f"index_entries={indexed_rows} "
        f"embed_p50_p95={_fmt_pair(embed_samples)} "
        f"redis_knn_p50_p95={_fmt_pair(knn_samples)} "
        "qdrant_p50_p95=n/a "
        "notes=L1_only_bench_brain_queries"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
