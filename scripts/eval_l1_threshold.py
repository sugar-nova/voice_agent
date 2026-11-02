#!/usr/bin/env python3
"""Offline threshold tuning for L1 semantic router."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "server"))

from app.brain.embeddings import FastEmbedder  # noqa: E402
from app.brain.l1 import InMemoryL1Router, try_build_redis_l1_router  # noqa: E402
from app.config import Settings  # noqa: E402
from app.kb.load import DEFAULT_FAQ_PATH, load_faqs  # noqa: E402

DEFAULT_EVAL_PATH = REPO_ROOT / "server" / "app" / "kb" / "eval_queries.yaml"


@dataclass(frozen=True)
class EvalQuery:
    text: str
    in_scope: bool
    expected_faq_id: str | None = None


@dataclass(frozen=True)
class ScoredQuery:
    query: EvalQuery
    similarity: float
    predicted_faq_id: str | None
    backend: str


def _parse_thresholds(raw: str) -> list[float]:
    values = [float(v.strip()) for v in raw.split(",") if v.strip()]
    if not values:
        raise ValueError("No thresholds provided")
    return values


def _load_eval_queries(path: Path) -> list[EvalQuery]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"{path}: expected a list of query fixtures")
    out: list[EvalQuery] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        in_scope = bool(item.get("in_scope", False))
        expected_faq_id = item.get("expected_faq_id")
        out.append(
            EvalQuery(
                text=text,
                in_scope=in_scope,
                expected_faq_id=str(expected_faq_id) if expected_faq_id else None,
            )
        )
    if not out:
        raise ValueError(f"{path}: no valid fixtures found")
    return out


def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _print_table_header() -> None:
    print(
        "threshold  precision  recall  f1    tp  fp  tn  fn  faq_hit_acc"
    )
    print(
        "---------  ---------  ------  ----  --  --  --  --  -----------"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--eval-file",
        type=Path,
        default=DEFAULT_EVAL_PATH,
        help=f"YAML fixtures file (default: {DEFAULT_EVAL_PATH})",
    )
    parser.add_argument(
        "--faq-file",
        type=Path,
        default=DEFAULT_FAQ_PATH,
        help=f"FAQ YAML file (default: {DEFAULT_FAQ_PATH})",
    )
    parser.add_argument(
        "--thresholds",
        default="0.90,0.92,0.94,0.95,0.96,0.97,0.98,0.99",
        help="Comma-separated threshold sweep values",
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    if settings.embedding_provider != "fastembed":
        print("Set EMBEDDING_PROVIDER=fastembed for this evaluator", file=sys.stderr)
        return 1

    entries = load_faqs(args.faq_file)
    eval_queries = _load_eval_queries(args.eval_file)
    embedder = FastEmbedder(settings.embedding_model)
    if settings.redis_url:
        l1 = try_build_redis_l1_router(
            entries=entries,
            embedder=embedder,
            redis_url=settings.redis_url,
            index_name=settings.redis_index_name,
        ) or InMemoryL1Router(entries, embedder)
    else:
        l1 = InMemoryL1Router(entries, embedder)

    scored: list[ScoredQuery] = []
    for query in eval_queries:
        result = l1.lookup(query.text)
        scored.append(
            ScoredQuery(
                query=query,
                similarity=result.similarity,
                predicted_faq_id=result.entry.id if result.entry else None,
                backend=result.backend,
            )
        )

    thresholds = _parse_thresholds(args.thresholds)
    print(
        f"fixtures={len(scored)} in_scope={sum(1 for s in scored if s.query.in_scope)} "
        f"out_scope={sum(1 for s in scored if not s.query.in_scope)} "
        f"backend={scored[0].backend if scored else 'unknown'}"
    )
    _print_table_header()

    best_threshold = thresholds[0]
    best_f1 = -1.0
    best_precision = 0.0
    for threshold in thresholds:
        tp = fp = tn = fn = 0
        faq_hits = 0
        faq_total = 0
        for item in scored:
            predicted_in_scope = item.similarity >= threshold
            actual_in_scope = item.query.in_scope
            if predicted_in_scope and actual_in_scope:
                tp += 1
            elif predicted_in_scope and not actual_in_scope:
                fp += 1
            elif not predicted_in_scope and not actual_in_scope:
                tn += 1
            else:
                fn += 1

            if actual_in_scope and item.query.expected_faq_id:
                faq_total += 1
                if predicted_in_scope and item.predicted_faq_id == item.query.expected_faq_id:
                    faq_hits += 1

        precision = _safe_div(tp, tp + fp)
        recall = _safe_div(tp, tp + fn)
        f1 = _safe_div(2 * precision * recall, precision + recall)
        faq_hit_acc = _safe_div(faq_hits, faq_total)
        print(
            f"{threshold:9.2f}  {_pct(precision):>9}  {_pct(recall):>6}  {_pct(f1):>4}  "
            f"{tp:2d}  {fp:2d}  {tn:2d}  {fn:2d}  {_pct(faq_hit_acc):>11}"
        )

        if f1 > best_f1 or (f1 == best_f1 and precision > best_precision):
            best_f1 = f1
            best_threshold = threshold
            best_precision = precision

    print()
    print(
        f"best_threshold={best_threshold:.2f} best_f1={best_f1:.3f} "
        f"tie_break=precision"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
