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
from geo_lib import gap_verdict, mentioned, read_json, section_named, sentence_word_count, split_sentences  # noqa: E402
from eval_judge import calibrate_scores, heuristic_judge, select_judge_provider  # noqa: E402


def test_mention_and_gap() -> None:
    assert mentioned("HubSpot", ["HubSpot is a frequent pick"])
    assert not mentioned("Acme", ["HubSpot is a frequent pick"])
    assert not mentioned("Acme", ["Acme is not mentioned in this overview."])
    assert not mentioned("Hub", ["HubSpot is a frequent pick"])
    assert mentioned("Zoom Info", ["ZoomInfo is a frequent pick"])
    assert gap_verdict("Acme", "HubSpot", False, True) == "competitor cited; brand absent"


def test_offline_overview_accepts_any_competitor() -> None:
    from apify_fetcher import ensure_names_in_offline_overview

    source = read_json(ROOT / "fixtures" / "serp_sample.json")
    adapted = ensure_names_in_offline_overview(source, "Nimbus", "ZoomInfo")
    adapted = attach_mentions(adapted, "Nimbus", "ZoomInfo")
    assert "ZoomInfo" in adapted["ai_overview_text"]
    assert adapted["competitor_mentioned_in_ai"] is True
    assert adapted["brand_mentioned_in_ai"] is False
    assert adapted["gap"] == "competitor cited; brand absent"


def test_parse_ddg_html_skips_ads_and_unwraps_urls() -> None:
    from apify_fetcher import build_ddg_payload, parse_ddg_html
    from geo_lib import extract_numbers

    html = (ROOT / "fixtures" / "ddg_sample.html").read_text(encoding="utf-8")
    rows = parse_ddg_html(html)
    titles = [row["title"] for row in rows]
    assert "Best seaweed snacks for 2026 | PCMag" in titles
    assert "Can cats eat seaweed? ASPCA" in titles
    assert "Buy TidePod LLC now" not in titles
    pcmag = next(row for row in rows if "PCMag" in row["title"])
    assert pcmag["url"] == "https://www.pcmag.com/picks/seaweed-snacks"
    assert "12 brands" in pcmag["snippet"]

    payload = build_ddg_payload(
        "best seaweed snacks for cats who do yoga",
        "PlanktonForge",
        "TidePod LLC",
        html,
    )
    assert payload is not None
    assert payload["source"] == "duckduckgo-html"
    overview = payload["ai_overview_text"]
    assert "Roasted nori sheets" in overview
    assert "99%" not in overview
    assert extract_numbers(overview) <= extract_numbers(html.replace("99%", ""))
    assert payload["brand_mentioned_in_ai"] is False
    assert payload["competitor_mentioned_in_ai"] is False
    assert payload["organic"]


def test_ddg_anomaly_html_has_no_results() -> None:
    from apify_fetcher import build_ddg_payload, build_unavailable_payload, ddg_html_blocked

    html = '<html><div class="anomaly-modal__title">Unfortunately, bots use DuckDuckGo too.</div></html>'
    assert ddg_html_blocked(html) is True
    assert build_ddg_payload("best bicycle bells for quiet librarians", "Dingwell", "Schwinn", html) is None
    payload = build_unavailable_payload(
        "best bicycle bells for quiet librarians", "Dingwell", "Schwinn", "ddg-empty"
    )
    blob = json.dumps(payload)
    assert payload["query"] == "best bicycle bells for quiet librarians"
    assert payload["source"] == "unavailable:ddg-empty"
    assert "HubSpot" not in blob
    assert "64%" not in blob
    assert "bicycle bells" in payload["ai_overview_text"]


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


def test_calibrate_scores_lifts_hedged_groundedness() -> None:
    payload = calibrate_scores(
        {
            "claims": [
                {"claim": "64% of buyers started free", "supported": True},
                {"claim": "HubSpot is cited", "supported": True},
            ],
            "scores": {
                "context_relevance": 1.0,
                "groundedness": 0.5,
                "answer_relevance": 0.5,
            },
        }
    )
    assert payload["scores"]["groundedness"] >= 0.9
    assert payload["scores"]["answer_relevance"] == 0.5


def test_stage_demo_auto_heuristic() -> None:
    import subprocess

    result = subprocess.run(
        [sys.executable, str(ROOT / "demo.py"), "--auto", "--judge", "heuristic", "--no-web", "--offline"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "GAP" in result.stdout
    assert "PASS" in result.stdout


def test_stage_demo_writes_show_html(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    monkeypatch.setenv("GEO_DEMO_NO_OPEN", "1")
    result = subprocess.run(
        [sys.executable, str(ROOT / "demo.py"), "--auto", "--judge", "heuristic", "--web", "--offline"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    board = (ROOT / "demo" / "show.html").read_text(encoding="utf-8")
    assert "competitor cited" in board
    assert "PASS" in board


def test_skill_runs_when_copied_alone(tmp_path: Path) -> None:
    import os
    import shutil
    import subprocess

    src = ROOT / ".agents" / "skills" / "geo-citation-engineer"
    dest = tmp_path / "geo-citation-engineer"
    shutil.copytree(src, dest)
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    fetcher = subprocess.run(
        [
            sys.executable,
            str(dest / "scripts" / "apify_fetcher.py"),
            "--offline",
            "--query",
            "best crm for startups",
            "--brand",
            "Acme",
            "--competitor",
            "HubSpot",
            "--out",
            "serp.json",
        ],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert fetcher.returncode == 0, fetcher.stderr + fetcher.stdout
    payload = json.loads((dest / "serp.json").read_text(encoding="utf-8"))
    assert payload["competitor_mentioned_in_ai"] is True
    assert payload["brand_mentioned_in_ai"] is False

    compliance = subprocess.run(
        [
            sys.executable,
            str(dest / "scripts" / "geo_compliance.py"),
            "--rewrite",
            "fixtures/rewrite.md",
            "--source",
            "serp.json",
        ],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert compliance.returncode == 0, compliance.stderr + compliance.stdout
    assert json.loads(compliance.stdout)["pass"] is True

    judged = subprocess.run(
        [
            sys.executable,
            str(dest / "scripts" / "eval_judge.py"),
            "--offline",
            "--judge",
            "heuristic",
            "--query",
            "best crm for startups",
            "--rewrite",
            "fixtures/rewrite.md",
            "--source",
            "serp.json",
            "--original-draft",
            "fixtures/draft.md",
        ],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert judged.returncode == 0, judged.stderr + judged.stdout
    assert json.loads(judged.stdout)["pass"] is True


def test_geo_rewrite_passes_compliance_for_default_fixture() -> None:
    from geo_rewrite import render_report

    source = read_json(ROOT / "fixtures" / "serp_sample.json")
    quotes = quotes_from_reviews(read_json(ROOT / "fixtures" / "g2_sample.json"))
    source = attach_mentions({**source, "quotes": quotes}, "Acme", "HubSpot")
    report = render_report(source, "Acme", "HubSpot")
    result = evaluate(report, source)
    assert result["pass"], json.dumps(result, indent=2)


def test_geo_rewrite_keeps_draft_intent() -> None:
    from geo_rewrite import render_report

    source = read_json(ROOT / "fixtures" / "serp_sample.json")
    source = attach_mentions(source, "Nimbus", "ZoomInfo")
    draft = "# Nimbus pipeline for seed teams\n\nWe help founders stop living in a spreadsheet."
    report = render_report(source, "Nimbus", "ZoomInfo", draft=draft)
    assert "Nimbus pipeline for seed teams" in report
    result = evaluate(report, source)
    assert result["pass"], json.dumps(result, indent=2)


def test_geo_rewrite_skips_draft_for_other_brand() -> None:
    from geo_rewrite import render_report

    source = read_json(ROOT / "fixtures" / "serp_sample.json")
    source = attach_mentions(source, "Kettleghost", "Nespresso")
    draft = "# Why Silt & Co makes calm moss lamps\n\nAquarium copy."
    report = render_report(source, "Kettleghost", "Nespresso", draft=draft)
    body = section_named(report, "Rewritten page") or report
    assert "moss lamps" not in body.lower()
    assert "Kettleghost" in body


def test_stage_demo_veridion_labels_skip_acme_quote() -> None:
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "demo.py"),
            "--auto",
            "--judge",
            "heuristic",
            "--no-web",
            "--offline",
            "--brand",
            "Veridion",
            "--competitor",
            "HubSpot",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr + result.stdout
    assert "VERIDION" in result.stdout
    assert "HUBSPOT" in result.stdout
    report = (ROOT / "demo" / "output" / "geo-report.md").read_text(encoding="utf-8")
    assert "Veridion" in report
    assert "replaced our spreadsheet" not in report.lower()
