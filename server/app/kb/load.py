"""Load curated FAQ YAML (M4B-02)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

KB_DIR = Path(__file__).resolve().parent
DEFAULT_FAQ_PATH = KB_DIR / "faqs.yaml"


@dataclass(frozen=True)
class FaqEntry:
    id: str
    question: str
    embedded_questions: tuple[str, ...]
    answer: str
    category: str
    tags: tuple[str, ...]


def load_faqs(path: Path | None = None) -> list[FaqEntry]:
    faq_path = path or DEFAULT_FAQ_PATH
    raw = yaml.safe_load(faq_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{faq_path}: expected a list of FAQ entries")
    entries: list[FaqEntry] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        question = str(item.get("question", "")).strip()
        embedded_questions_raw = item.get("embedded_questions", [])
        embedded_questions = tuple(
            str(q).strip() for q in embedded_questions_raw if str(q).strip()
        )
        if not question and embedded_questions:
            question = embedded_questions[0]
        if question and question not in embedded_questions:
            embedded_questions = (question, *embedded_questions)
        if not question:
            raise ValueError(f"{faq_path}: FAQ entry missing question/embedded_questions")
        if not embedded_questions:
            embedded_questions = (question,)
        entries.append(
            FaqEntry(
                id=str(item["id"]),
                question=question,
                embedded_questions=embedded_questions,
                answer=str(item["answer"]).strip(),
                category=str(item.get("category", "general")),
                tags=tuple(str(t) for t in item.get("tags", [])),
            )
        )
    if not entries:
        raise ValueError(f"{faq_path}: no FAQ entries found")
    return entries
