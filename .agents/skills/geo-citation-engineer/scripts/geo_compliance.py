#!/usr/bin/env python3
"""Deterministic GEO compliance score for a rewritten page."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from geo_lib import (
    body_sentences,
    extract_numbers,
    extract_quoted_spans,
    has_list_block,
    load_dotenv,
    read_json,
    section_named,
    sentence_word_count,
    write_json,
)

HARD_MAX_WORDS = 18
TARGET_MAX_WORDS = 15


def evaluate(rewrite: str, source: dict | None) -> dict:
    scoped = section_named(rewrite, "Rewritten page") or rewrite
    sentences = body_sentences(scoped)
    lengths = [sentence_word_count(s) for s in sentences]
    over_hard = [
        {"sentence": s, "words": n} for s, n in zip(sentences, lengths) if n > HARD_MAX_WORDS
    ]
    within_target = sum(1 for n in lengths if 1 <= n <= TARGET_MAX_WORDS)
    ratio = (within_target / len(lengths)) if lengths else 0.0

    source_text = ""
    quotes_expected = []
    if source:
        source_text = " ".join(
            [
                str(source.get("ai_overview_text") or ""),
                str(source.get("query") or ""),
                str(source.get("gap") or ""),
                " ".join(source.get("people_also_ask") or []),
                " ".join(source.get("related_queries") or []),
                " ".join(source.get("fan_out") or []),
                " ".join(
                    f"{row.get('title','')} {row.get('url','')} {row.get('snippet','')}"
                    for row in (source.get("cited_sources") or []) + (source.get("organic") or [])
                ),
                " ".join(q.get("quote", "") for q in source.get("quotes") or []),
                " ".join((source.get("brand_facts") or {}).get("claims") or []),
            ]
        )
        quotes_expected = source.get("quotes") or []

    source_numbers = extract_numbers(source_text)
    rewrite_numbers = extract_numbers(scoped)
    list_ok = has_list_block(scoped)
    quoted = extract_quoted_spans(scoped)

    checks: list[dict] = []

    def add(name: str, passed: bool, detail: str, weight: float) -> None:
        checks.append({"name": name, "pass": passed, "detail": detail, "weight": weight})

    add(
        "sentences_present",
        bool(sentences),
        f"{len(sentences)} prose sentences",
        0.1,
    )
    add(
        "target_sentence_length",
        ratio >= 0.85 and bool(sentences),
        f"{ratio:.0%} of sentences have <= {TARGET_MAX_WORDS} words",
        0.3,
    )
    add(
        "no_overlong_sentence",
        not over_hard,
        "none" if not over_hard else f"{len(over_hard)} sentence(s) over {HARD_MAX_WORDS} words",
        0.25,
    )
    add(
        "list_structure",
        list_ok,
        "found a markdown list" if list_ok else "no list markers",
        0.15,
    )

    if source_numbers:
        overlap = source_numbers & rewrite_numbers
        invented = rewrite_numbers - source_numbers
        add(
            "sourced_statistic",
            bool(overlap) and not invented,
            f"shared={sorted(overlap)} invented={sorted(invented)}",
            0.15,
        )
    else:
        add(
            "no_invented_statistic",
            not rewrite_numbers,
            "source had no numbers; rewrite must not invent any"
            if rewrite_numbers
            else "no numbers in source or rewrite",
            0.15,
        )

    if quotes_expected:
        add(
            "quote_present",
            bool(quoted),
            f"{len(quoted)} quoted span(s)" if quoted else "G2 quotes were available but unused",
            0.05,
        )
    else:
        add("quote_optional", True, "no G2 quotes in source JSON", 0.05)

    weighted = sum(c["weight"] for c in checks if c["pass"])
    total_weight = sum(c["weight"] for c in checks) or 1.0
    score = round(weighted / total_weight, 3)
    passed = all(c["pass"] for c in checks)

    return {
        "geo_compliance_score": score,
        "pass": passed,
        "sentence_count": len(sentences),
        "target_length_ratio": round(ratio, 3),
        "over_hard_max": over_hard,
        "checks": checks,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score GEO structural compliance.")
    parser.add_argument("--rewrite", required=True, help="Path to rewritten markdown")
    parser.add_argument("--source", default=None, help="Path to fetcher JSON")
    parser.add_argument("--out", default=None, help="Optional JSON output path")
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    rewrite_path = Path(args.rewrite)
    if not rewrite_path.is_file():
        print(f"rewrite not found: {rewrite_path}", file=sys.stderr)
        return 1
    rewrite = rewrite_path.read_text(encoding="utf-8")
    source = read_json(Path(args.source)) if args.source else None
    if args.source and not isinstance(source, dict):
        print("source JSON must be an object", file=sys.stderr)
        return 1
    result = evaluate(rewrite, source if isinstance(source, dict) else None)
    rendered = write_json(result)
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if result["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
