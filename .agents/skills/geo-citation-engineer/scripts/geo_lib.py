"""Shared helpers for GEO fetch, compliance, and eval scripts."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Iterable

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"[A-Za-z0-9']+")
NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?%?\b")
LIST_RE = re.compile(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+\S")
QUOTE_RE = re.compile(r"[“”\"']([^“”\"']{8,240})[“”\"']")


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "fixtures").is_dir() and (candidate / "LICENSE").is_file():
            return candidate
        if (candidate / ".agents" / "skills" / "geo-citation-engineer" / "SKILL.md").is_file() and (
            candidate / "README.md"
        ).is_file():
            return candidate
    return here.parents[4]


def skill_dir() -> Path:
    return Path(__file__).resolve().parents[1]


def load_dotenv() -> None:
    path = repo_root() / ".env"
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def tokenize_words(text: str) -> list[str]:
    return WORD_RE.findall(text or "")


def sentence_word_count(sentence: str) -> int:
    return len(tokenize_words(sentence))


def split_sentences(text: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", (text or "").strip())
    if not cleaned:
        return []
    parts = SENTENCE_SPLIT.split(cleaned)
    sentences: list[str] = []
    for part in parts:
        chunk = part.strip()
        if not chunk:
            continue
        sentences.append(chunk)
    return sentences


def section_named(markdown: str, heading: str) -> str | None:
    """Return the markdown body under an H2 heading, or None if absent."""
    lines = (markdown or "").splitlines()
    pattern = re.compile(rf"^##\s+{re.escape(heading)}\s*$", re.I)
    start = None
    for index, line in enumerate(lines):
        if pattern.match(line.strip()):
            start = index + 1
            break
    if start is None:
        return None
    end = len(lines)
    for index in range(start, len(lines)):
        if re.match(r"^##\s+\S", lines[index]) and not lines[index].startswith("###"):
            end = index
            break
    return "\n".join(lines[start:end]).strip()


def body_sentences(markdown: str) -> list[str]:
    """Sentences from rewrite prose, skipping headings and list markers for length checks.

    List items still count as sentences after stripping the marker.
    """
    sentences: list[str] = []
    for raw_line in (markdown or "").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("|") or set(line) <= set("-|: "):
            continue
        line = re.sub(r"^[-*•]\s+", "", line)
        line = re.sub(r"^\d+[.)]\s+", "", line)
        sentences.extend(split_sentences(line))
    return sentences


def extract_numbers(text: str) -> set[str]:
    return {match.group(0) for match in NUMBER_RE.finditer(text or "")}


def has_list_block(markdown: str) -> bool:
    return bool(LIST_RE.search(markdown or ""))


def extract_quoted_spans(text: str) -> list[str]:
    return [match.group(1).strip() for match in QUOTE_RE.finditer(text or "")]


def mentioned(needle: str, haystacks: Iterable[str]) -> bool:
    needle_norm = (needle or "").strip().lower()
    if len(needle_norm) < 2:
        return False
    blob = " ".join(h or "" for h in haystacks).lower()
    if needle_norm in blob:
        return True
    compact = re.sub(r"[^a-z0-9]+", "", needle_norm)
    blob_compact = re.sub(r"[^a-z0-9]+", "", blob)
    return bool(compact) and compact in blob_compact


def gap_verdict(brand: str, competitor: str | None, brand_hit: bool, competitor_hit: bool) -> str:
    if brand_hit and competitor_hit:
        return "both brand and competitor cited"
    if brand_hit and not competitor_hit:
        return "brand cited; competitor absent"
    if competitor_hit and not brand_hit:
        return "competitor cited; brand absent"
    if competitor:
        return "neither brand nor competitor cited"
    return "brand absent from AI overview"


def clip_quote(text: str, min_words: int = 6, max_words: int = 15) -> str | None:
    for sentence in split_sentences(text):
        words = tokenize_words(sentence)
        if min_words <= len(words) <= max_words:
            clipped = " ".join(words)
            return clipped
        if len(words) > max_words:
            clipped = " ".join(words[:max_words])
            return clipped
    words = tokenize_words(text)
    if len(words) < min_words:
        return None
    return " ".join(words[:max_words])
