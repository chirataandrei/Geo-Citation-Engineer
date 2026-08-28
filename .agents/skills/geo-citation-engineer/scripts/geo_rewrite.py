#!/usr/bin/env python3
"""Deterministic GEO rewrite from fetcher JSON. Stdlib only. No invented stats."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from geo_lib import (  # noqa: E402
    extract_numbers,
    load_dotenv,
    quotes_for_brand,
    read_json,
    sentence_word_count,
    split_sentences,
)

MAX_WORDS = 15


def cap_sentence(text: str, max_words: int = MAX_WORDS) -> str:
    words = [part for part in (text or "").strip().split() if part]
    if not words:
        return ""
    clipped = " ".join(words[:max_words]).rstrip(".")
    return clipped + "."


def source_blob(source: dict[str, Any]) -> str:
    parts = [
        str(source.get("ai_overview_text") or ""),
        str(source.get("query") or ""),
        str(source.get("gap") or ""),
        " ".join(str(item) for item in (source.get("fan_out") or [])),
        " ".join(
            f"{row.get('title', '')} {row.get('snippet', '')}"
            for row in (source.get("cited_sources") or []) + (source.get("organic") or [])
            if isinstance(row, dict)
        ),
        " ".join(str(q.get("quote") or "") for q in (source.get("quotes") or []) if isinstance(q, dict)),
    ]
    return " ".join(parts)


def sourced_stat_sentence(source: dict[str, Any]) -> str | None:
    overview = str(source.get("ai_overview_text") or "")
    numbers = extract_numbers(overview)
    if not numbers:
        return None
    for sentence in split_sentences(overview):
        if extract_numbers(sentence) & numbers:
            return cap_sentence(sentence)
    first = sorted(numbers)[0]
    return cap_sentence(f"{first} appears in the AI Overview.")


def rewritten_page(source: dict[str, Any], brand: str, competitor: str | None) -> str:
    query = str(source.get("query") or "this query")
    gap = str(source.get("gap") or "")
    brand_hit = bool(source.get("brand_mentioned_in_ai"))
    competitor_hit = bool(source.get("competitor_mentioned_in_ai"))
    quotes = quotes_for_brand(source.get("quotes") or [], brand)
    fan = [str(item) for item in (source.get("fan_out") or []) if str(item).strip()]
    lines: list[str] = []

    lines.append(cap_sentence(f"{brand} is a first-party page for {query}"))
    stat = sourced_stat_sentence(source)
    if stat:
        lines.append(stat)
    lines.append("")

    if competitor and competitor_hit:
        lines.append(cap_sentence(f"{competitor} is named in the AI Overview"))
    elif competitor:
        lines.append(cap_sentence(f"{competitor} is not named in the AI Overview"))
    if brand_hit:
        lines.append(cap_sentence(f"{brand} is cited in that AI Overview"))
    else:
        lines.append(cap_sentence(f"{brand} is absent from that AI Overview"))
    if gap:
        lines.append(cap_sentence(f"The citation gap is {gap}"))
    lines.append("")

    bullets: list[str] = []
    if stat:
        bullets.append(f"- {stat}")
    if competitor:
        if competitor_hit:
            bullets.append(f"- {cap_sentence(f'{competitor} remains the cited default pick')}")
        else:
            bullets.append(f"- {cap_sentence(f'{competitor} is also absent from this overview')}")
    bullets.append(f"- {cap_sentence(f'{brand} targets this query, not a generic essay')}")

    heads = fan[:3] or [query]
    for index, heading in enumerate(heads):
        lines.append(f"### {heading}")
        lines.append("")
        lines.append(cap_sentence(f"Cover {heading}"))
        if index == 0:
            lines.append("")
            lines.extend(bullets)
        lines.append("")

    if quotes:
        row = quotes[0]
        quote = str(row.get("quote") or "").strip()
        reviewer = str(row.get("reviewer") or "G2 reviewer").strip()
        if quote:
            lines.append(f'{reviewer} on G2: "{quote}"')
            lines.append("")

    body = "\n".join(lines).strip() + "\n"
    over = [s for s in split_sentences(body) if sentence_word_count(s) > 18]
    if over:
        # Last-resort cap; should not fire if templates stay short.
        rebuilt = []
        for line in body.splitlines():
            if line.startswith("#") or line.startswith("-") or not line.strip():
                rebuilt.append(line)
                continue
            rebuilt.append(cap_sentence(line, 15) if sentence_word_count(line) > 15 else line)
        body = "\n".join(rebuilt).strip() + "\n"
    return body


def render_report(source: dict[str, Any], brand: str, competitor: str | None) -> str:
    query = str(source.get("query") or "")
    gap = str(source.get("gap") or "")
    fetched = str(source.get("fetched_at") or "")
    brand_hit = source.get("brand_mentioned_in_ai")
    competitor_hit = source.get("competitor_mentioned_in_ai")
    sources = source.get("cited_sources") or []
    source_lines = []
    for row in sources:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or "Source")
        url = str(row.get("url") or "")
        snippet = str(row.get("snippet") or "")
        if url:
            source_lines.append(f"- [{title}]({url}) — {snippet}".rstrip(" —"))
        else:
            source_lines.append(f"- {title} — {snippet}".rstrip(" —"))
    if not source_lines:
        source_lines.append("- None returned in this fetch.")
    fan = source.get("fan_out") or []
    fan_lines = [f"- {item}" for item in fan] or ["- (no fan-out in JSON)"]
    if competitor and not competitor_hit and not brand_hit:
        gap_summary = f"The AI Overview does not cite {brand} or {competitor}."
    elif competitor_hit and not brand_hit:
        gap_summary = f"The AI Overview names {competitor}. It does not cite {brand}."
    elif brand_hit and competitor and not competitor_hit:
        gap_summary = f"The AI Overview names {brand}. It does not cite {competitor}."
    elif brand_hit:
        gap_summary = f"The AI Overview already names {brand}."
    else:
        gap_summary = f"The AI Overview does not cite {brand}."

    body = rewritten_page(source, brand, competitor)
    comp_label = competitor or "—"
    change_rows = [
        f"| Gap verdict | gap | {gap or 'n/a'} |",
        "| Sourced claims | ai_overview_text, cited_sources | Copied; not invented |",
        "| Fan-out H2s | fan_out | PAA and related queries |",
    ]
    if quotes_for_brand(source.get("quotes") or [], brand):
        change_rows.append("| G2 quote | quotes | Brand-matched span only |")
    return "\n".join(
        [
            f"# GEO report: {query}",
            "",
            f"Brand: **{brand}**",
            f"Competitor: {comp_label}",
            f"Fetched: {fetched}",
            "",
            "## Citation gap",
            "",
            f"- Verdict: {gap}",
            f"- Brand mentioned in AI Overview: {brand_hit}",
            f"- Competitor mentioned in AI Overview: {competitor_hit}",
            "",
            gap_summary,
            "",
            "## Sources the engine already cites",
            "",
            *source_lines,
            "",
            "## Fan-out map",
            "",
            *fan_lines,
            "",
            "## Rewritten page",
            "",
            body.rstrip(),
            "",
            "## Change log",
            "",
            "| Change | JSON field | Notes |",
            "| --- | --- | --- |",
            *change_rows,
            "",
        ]
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a GEO report from fetcher JSON.")
    parser.add_argument("--source", required=True, help="Fetcher JSON path")
    parser.add_argument("--draft", default=None, help="Original draft (unused for facts; kept for the agent)")
    parser.add_argument("--brand", required=True)
    parser.add_argument("--competitor", default=None)
    parser.add_argument("--out", required=True)
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    source_path = Path(args.source)
    if not source_path.is_file():
        print(f"source not found: {source_path}", file=sys.stderr)
        return 1
    source = read_json(source_path)
    if not isinstance(source, dict):
        print("source JSON must be an object", file=sys.stderr)
        return 1
    if args.draft:
        draft_path = Path(args.draft)
        if not draft_path.is_file():
            print(f"draft not found: {draft_path}", file=sys.stderr)
            return 1
    report = render_report(source, args.brand, args.competitor)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
