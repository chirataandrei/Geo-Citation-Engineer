from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".agents" / "skills" / "geo-citation-engineer" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from apify_fetcher import attach_mentions, build_payload, quotes_from_reviews  # noqa: E402
from geo_compliance import evaluate  # noqa: E402
from geo_lib import gap_verdict, mentioned, read_json, sentence_word_count, split_sentences  # noqa: E402
from eval_judge import heuristic_judge  # noqa: E402


def test_mention_and_gap() -> None:
    assert mentioned("HubSpot", ["HubSpot is a frequent pick"])
    assert not mentioned("Acme", ["HubSpot is a frequent pick"])
    assert gap_verdict("Acme", "HubSpot", False, True) == "competitor cited; brand absent"


def test_normalize_raw_serp() -> None:
    raw = read_json(ROOT / "fixtures" / "serp_raw.json")
    payload = build_payload(
        query="best crm for startups",
        brand="Acme",
        competitor="HubSpot",
        serp_items=[raw],
        quotes=[],
        source="test",
    )
    assert "HubSpot" in payload["ai_overview_text"]
    assert payload["competitor_mentioned_in_ai"] is True
    assert payload["brand_mentioned_in_ai"] is False
    assert payload["fan_out"]
    assert payload["cited_sources"][0]["url"].startswith("https://")


def test_g2_quote_length() -> None:
    reviews = read_json(ROOT / "fixtures" / "g2_sample.json")
    quotes = quotes_from_reviews(reviews)
    assert quotes
    words = quotes[0]["quote"].split()
    assert 6 <= len(words) <= 15


def test_compliance_good_rewrite() -> None:
    source = read_json(ROOT / "fixtures" / "serp_sample.json")
    quotes = quotes_from_reviews(read_json(ROOT / "fixtures" / "g2_sample.json"))
    source = attach_mentions({**source, "quotes": quotes}, "Acme", "HubSpot")
    rewrite = (ROOT / "fixtures" / "rewrite.md").read_text(encoding="utf-8")
    result = evaluate(rewrite, source)
    assert result["pass"], json.dumps(result, indent=2)
    assert result["geo_compliance_score"] >= 0.85


def test_compliance_bad_rewrite() -> None:
    source = read_json(ROOT / "fixtures" / "serp_sample.json")
    rewrite = (ROOT / "fixtures" / "rewrite_bad.md").read_text(encoding="utf-8")
    result = evaluate(rewrite, source)
    assert result["pass"] is False
    names = {c["name"]: c["pass"] for c in result["checks"]}
    assert names["no_overlong_sentence"] is False
    assert names["sourced_statistic"] is False or names.get("no_invented_statistic") is False


def test_heuristic_judge_rejects_invented_stats() -> None:
    source = read_json(ROOT / "fixtures" / "serp_sample.json")
    judged = heuristic_judge(
        "best crm for startups",
        (ROOT / "fixtures" / "rewrite_bad.md").read_text(encoding="utf-8"),
        source,
    )
    assert judged["pass"] is False
    assert judged["invented_numbers"]
    assert judged["scores"]["groundedness"] == 0.0


def test_sentence_split_helper() -> None:
    sentences = split_sentences("Acme ships weekly. HubSpot is cited.")
    assert len(sentences) == 2
    assert sentence_word_count(sentences[0]) == 3
