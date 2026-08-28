"""Shared helpers for GEO fetch, compliance, and eval scripts."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Iterable

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
WORD_RE = re.compile(r"[A-Za-z0-9']+")
NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)?%?\b")
LIST_RE = re.compile(r"(?m)^\s*(?:[-*•]|\d+[.)])\s+\S")
QUOTE_RE = re.compile(r"[“”\"']([^“”\"']{8,240})[“”\"']")


def skill_dir() -> Path:
    """Directory that contains SKILL.md — works even when the skill is copied alone."""
    return Path(__file__).resolve().parents[1]


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "demo.py").is_file() and (candidate / "submission.json").is_file():
            return candidate
        if (candidate / ".agents" / "skills" / "geo-citation-engineer" / "SKILL.md").is_file() and (
            candidate / "README.md"
        ).is_file():
            return candidate
    return skill_dir()


def fixture_file(name: str) -> Path:
    """Resolve an offline fixture. Skill copy first, then git-repo fixtures/."""
    relative = Path(name)
    if relative.is_absolute() and relative.is_file():
        return relative
    filename = relative.name if relative.parts[0] == "fixtures" else relative
    if relative.parts[:1] == ("fixtures",) and len(relative.parts) > 1:
        filename = Path(*relative.parts[1:])
    skill_hit = skill_dir() / "fixtures" / filename
    if skill_hit.is_file():
        return skill_hit
    cwd_hit = Path.cwd() / relative
    if cwd_hit.is_file():
        return cwd_hit
    repo_hit = repo_root() / "fixtures" / filename
    return repo_hit


def _parse_dotenv(path: Path) -> None:
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


def load_dotenv() -> None:
    seen: set[Path] = set()
    candidates = [
        Path(os.environ["GEO_DOTENV"]) if os.environ.get("GEO_DOTENV") else None,
        Path.cwd() / ".env",
        skill_dir() / ".env",
        repo_root() / ".env",
    ]
    here = Path.cwd()
    for parent in [here, *here.parents]:
        candidates.append(parent / ".env")
        if len(candidates) > 12:
            break
    for path in candidates:
        if path is None:
            continue
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        _parse_dotenv(path)


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
    token = re.compile(rf"\b{re.escape(needle_norm)}\b", re.I)
    negated = re.compile(
        r"\b(not mentioned|no mention|is absent|are absent|not cited|isn't cited|is not cited|does not cite)\b",
        re.I,
    )
    for hay in haystacks:
        text = hay or ""
        sentences = split_sentences(text) or [text]
        for sentence in sentences:
            if not token.search(sentence):
                continue
            if negated.search(sentence):
                continue
            return True
        hay_tokens = [tok.lower() for tok in re.findall(r"[a-z0-9]+", text.lower())]
        needle_tokens = [tok.lower() for tok in re.findall(r"[a-z0-9]+", needle_norm)]
        compact_needle = "".join(needle_tokens)
        compact_hit = False
        if compact_needle:
            for start in range(len(hay_tokens)):
                acc = ""
                for tok in hay_tokens[start:]:
                    acc += tok
                    if acc == compact_needle:
                        compact_hit = True
                        break
                    if len(acc) > len(compact_needle):
                        break
                if compact_hit:
                    break
        if compact_hit and not negated.search(text):
            return True
    return False


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


def quote_matches_brand(quote: dict[str, Any], brand: str) -> bool:
    needle = (brand or "").strip()
    if len(needle) < 2:
        return False
    product = str(quote.get("product") or quote.get("productName") or "")
    text = str(quote.get("quote") or quote.get("reviewText") or "")
    reviewer = str(quote.get("reviewer") or quote.get("reviewerName") or "")
    return mentioned(needle, [product, text, reviewer])


def quotes_for_brand(quotes: Iterable[dict[str, Any]], brand: str) -> list[dict[str, Any]]:
    return [row for row in quotes if isinstance(row, dict) and quote_matches_brand(row, brand)]


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
