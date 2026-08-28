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
from eval_judge import heuristic_judge, select_judge_provider  # noqa: E402


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


def test_select_judge_prefers_gemini_without_anthropic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    assert select_judge_provider("auto") == "gemini"
    assert select_judge_provider("gemini") == "gemini"
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert select_judge_provider("auto") == "heuristic"


# --------------------------------------------------------------------------- #
# run_geo orchestrator: the three decision paths and the fact-budget split
# --------------------------------------------------------------------------- #

from run_geo import (  # noqa: E402
    allowed_facts,
    build_evidence,
    citing_sources,
    classify,
    rank_fan_out,
)

BRIEFS = ROOT / "demo" / "input"


def _case(name: str) -> dict:
    brief = read_json(BRIEFS / f"{name}.brief.json")
    snapshot = read_json(ROOT / brief["snapshot"])
    return {"brief": brief, "evidence": build_evidence(brief, snapshot)}


def _action(name: str) -> str:
    case = _case(name)
    return classify(case["evidence"], allowed_facts(case["evidence"])["all_numbers"])["action"]


def test_intended_use_detects_real_gap() -> None:
    """Case 1: competitor in the citable set, brand absent -> rewrite."""
    evidence = _case("bible-chat")["evidence"]
    assert evidence["competitor_mentioned_in_ai"] is True
    assert evidence["brand_mentioned_in_ai"] is False
    assert evidence["gap"] == "competitor cited; brand absent"
    assert len(citing_sources(evidence, "YouVersion")) == 3
    assert citing_sources(evidence, "Bible Chat") == []
    assert _action("bible-chat") == "rewrite"


def test_thin_evidence_aborts_instead_of_inventing_a_gap() -> None:
    """Case 2: one source, no AI Overview -> refuse to claim a gap."""
    assert _action("thin-evidence") == "abort"


def test_already_cited_brand_declines_rewrite() -> None:
    """Case 3: same snapshot as case 1, brand swapped -> decline."""
    evidence = _case("youversion-already-cited")["evidence"]
    assert evidence["brand_mentioned_in_ai"] is True
    assert _action("youversion-already-cited") == "decline"


def test_same_snapshot_yields_opposite_verdicts() -> None:
    """The verdict comes from the evidence, not from the request."""
    a = _case("bible-chat")
    b = _case("youversion-already-cited")
    assert a["brief"]["snapshot"] == b["brief"]["snapshot"]
    assert _action("bible-chat") != _action("youversion-already-cited")


def test_reusability_new_industry_no_code_edits() -> None:
    """A new brief in an unrelated vertical works with no code change."""
    evidence = _case("attio")["evidence"]
    assert evidence["gap"] == "competitor cited; brand absent"
    assert _action("attio") == "rewrite"
    # No first-party facts collected, so nothing is assertable about the brand.
    assert allowed_facts(evidence)["brand_numbers"] == []


def test_fact_budget_keeps_competitor_numbers_out_of_brand_claims() -> None:
    """Olive Tree's 4.7 rating must never be assertable as the brand's."""
    facts = allowed_facts(_case("bible-chat")["evidence"])
    assert "40" in facts["brand_numbers"]
    assert "95%" in facts["brand_numbers"]
    assert "4.7" in facts["evidence_numbers"]
    assert "4.7" not in facts["brand_numbers"]
    assert "131,826" not in facts["brand_numbers"]
    assert not set(facts["brand_numbers"]) & set(facts["evidence_numbers"])


def test_number_extraction_survives_suffixed_magnitudes() -> None:
    """'40M' must yield '40' so '40 million' is not scored as invented."""
    from geo_lib import extract_numbers

    assert "40" in extract_numbers("Used by over 40M Christians")


def test_fan_out_ranking_drops_offtopic_and_duplicates() -> None:
    evidence = _case("bible-chat")["evidence"]
    priority = rank_fan_out(evidence["query"], evidence["fan_out"])
    assert len(priority) == 3
    assert "What does God say about left-handers?" not in priority
    assert all(item in evidence["fan_out"] for item in priority)

    crm = _case("attio")["evidence"]
    crm_priority = rank_fan_out(crm["query"], crm["fan_out"])
    token_sets = [frozenset(p.lower().split()) for p in crm_priority]
    assert len(set(token_sets)) == len(token_sets)


def test_committed_fallback_reports_still_pass_their_evals() -> None:
    """demo/output/ must stay green; it is what carries the demo if Codex stalls."""
    for name in ("bible-chat", "attio"):
        case = _case(name)
        report = (ROOT / "demo" / "output" / f"geo-report.{name}.md").read_text(encoding="utf-8")
        assert "AGENT-REWRITE" not in report
        compliance = evaluate(report, case["evidence"])
        assert compliance["pass"], (name, compliance["checks"])
        judged = heuristic_judge(case["evidence"]["query"], report, case["evidence"])
        assert judged["invented_numbers"] == [], (name, judged["invented_numbers"])
        assert judged["pass"], (name, judged["rationale"])


def test_snapshots_carry_honest_provenance() -> None:
    for path in sorted((BRIEFS / "snapshots").glob("*.json")):
        prov = read_json(path).get("provenance")
        assert prov, path
        assert prov["method"] in {"browser_capture", "synthetic_test_fixture"}, path
        if prov["method"] == "browser_capture":
            assert prov["request_url"], path
            assert prov["retrieved_at"], path
            assert prov["verbatim"] is True, path
        else:
            assert prov["retrieved_at"] is None, path
