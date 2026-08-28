#!/usr/bin/env python3
"""Fetch Google AI Overview + optional G2 quotes; emit normalized GEO JSON."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from geo_lib import (
    clip_quote,
    fixture_file,
    gap_verdict,
    load_dotenv,
    mentioned,
    quotes_for_brand,
    read_json,
    skill_dir,
    write_json,
)

SERP_ACTOR = "apify/google-search-scraper"
OVERVIEW_ACTOR = "apify/google-ai-overviews-scraper"
G2_ACTOR = "automation-lab/g2-scraper"
DEFAULT_WAIT_SECS = 280


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _text_of(item: Any) -> str:
    if item is None:
        return ""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        for key in ("question", "title", "text", "query", "name", "snippet", "description"):
            val = item.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    return str(item).strip()


def _source_record(item: Any) -> dict[str, str] | None:
    if not isinstance(item, dict):
        return None
    title = _text_of(item.get("title") or item.get("name") or "")
    url = str(item.get("url") or item.get("link") or "").strip()
    snippet = _text_of(item.get("description") or item.get("snippet") or item.get("text") or "")
    if not title and not url:
        return None
    return {"title": title, "url": url, "snippet": snippet}


def _extract_ai_block(item: dict[str, Any]) -> tuple[str, list[dict[str, str]]]:
    candidates: list[Any] = []
    for key in ("aiOverview", "aiOverviewResult", "aiModeResult", "aiMode"):
        if item.get(key):
            candidates.append(item[key])
    if item.get("text") and item.get("sources") is not None:
        candidates.append(item)

    text = ""
    sources: list[dict[str, str]] = []
    for block in candidates:
        if isinstance(block, str):
            if not text:
                text = block.strip()
            continue
        if not isinstance(block, dict):
            continue
        nested_text = (
            block.get("text")
            or block.get("answer")
            or block.get("content")
            or block.get("overview")
            or ""
        )
        if isinstance(nested_text, dict):
            nested_text = nested_text.get("text") or ""
        if isinstance(nested_text, str) and nested_text.strip() and not text:
            text = nested_text.strip()
        for src in _as_list(block.get("sources") or block.get("citations") or block.get("references")):
            record = _source_record(src)
            if record:
                sources.append(record)
    return text, sources


def normalize_serp_item(item: dict[str, Any], query: str) -> dict[str, Any]:
    ai_text, cited = _extract_ai_block(item)
    organic: list[dict[str, str]] = []
    for row in _as_list(item.get("organicResults") or item.get("organic") or []):
        record = _source_record(row)
        if record:
            organic.append(record)

    paa: list[str] = []
    for row in _as_list(item.get("peopleAlsoAsk") or item.get("people_also_ask") or []):
        text = _text_of(row)
        if text:
            paa.append(text)

    related: list[str] = []
    for row in _as_list(item.get("relatedQueries") or item.get("related_queries") or []):
        text = _text_of(row)
        if text:
            related.append(text)

    fan_out: list[str] = []
    seen: set[str] = set()
    for extra in paa + related:
        key = extra.lower()
        if key not in seen:
            seen.add(key)
            fan_out.append(extra)

    return {
        "query": query,
        "ai_overview_text": ai_text,
        "cited_sources": cited,
        "organic": organic[:10],
        "people_also_ask": paa,
        "related_queries": related,
        "fan_out": fan_out,
        "actor_item_keys": sorted(item.keys()),
    }


def attach_mentions(payload: dict[str, Any], brand: str, competitor: str | None) -> dict[str, Any]:
    haystacks = [
        payload.get("ai_overview_text") or "",
        *[s.get("title", "") for s in payload.get("cited_sources") or []],
        *[s.get("url", "") for s in payload.get("cited_sources") or []],
        *[s.get("snippet", "") for s in payload.get("cited_sources") or []],
    ]
    brand_hit = mentioned(brand, haystacks)
    competitor_hit = mentioned(competitor or "", haystacks) if competitor else False
    payload["brand"] = brand
    payload["competitor"] = competitor
    payload["brand_mentioned_in_ai"] = brand_hit
    payload["competitor_mentioned_in_ai"] = competitor_hit
    payload["gap"] = gap_verdict(brand, competitor, brand_hit, competitor_hit)
    return payload


def quotes_from_reviews(reviews: list[dict[str, Any]], limit: int = 3) -> list[dict[str, Any]]:
    ranked = sorted(
        reviews,
        key=lambda row: (
            float(row.get("starRating") or row.get("nps") or 0),
            int(row.get("helpfulVotes") or 0),
        ),
        reverse=True,
    )
    quotes: list[dict[str, Any]] = []
    for review in ranked:
        body = str(review.get("reviewText") or review.get("title") or "")
        span = clip_quote(body)
        if not span:
            continue
        quotes.append(
            {
                "quote": span,
                "reviewer": review.get("reviewerName") or "G2 reviewer",
                "nps": review.get("nps"),
                "star_rating": review.get("starRating"),
                "source_url": review.get("url") or "",
                "product": review.get("productName") or "",
            }
        )
        if len(quotes) >= limit:
            break
    return quotes


def _actor_call(client: Any, actor_id: str, run_input: dict[str, Any]) -> dict[str, Any]:
    return client.actor(actor_id).call(
        run_input=run_input,
        timeout_secs=DEFAULT_WAIT_SECS,
        wait_secs=DEFAULT_WAIT_SECS,
    )


def _dataset_items(client: Any, run: dict[str, Any], named: str | None = None) -> list[dict[str, Any]]:
    dataset_id = None
    storage = run.get("storageIds") or {}
    datasets = storage.get("datasets") or {}
    if named and datasets.get(named):
        dataset_id = datasets[named]
    dataset_id = dataset_id or run.get("defaultDatasetId")
    if not dataset_id:
        return []
    return list(client.dataset(dataset_id).iterate_items())


def fetch_serp_live(
    client: Any,
    query: str,
    country_code: str,
    language_code: str,
) -> list[dict[str, Any]]:
    run_input = {
        "queries": query,
        "maxPagesPerQuery": 1,
        "countryCode": country_code,
        "languageCode": language_code,
        "aiOverview": {"scrapeFullAiOverview": True},
    }
    run = _actor_call(client, SERP_ACTOR, run_input)
    return _dataset_items(client, run)


def fetch_overview_fallback(client: Any, query: str) -> list[dict[str, Any]]:
    run = _actor_call(client, OVERVIEW_ACTOR, {"queries": query})
    return _dataset_items(client, run)


def fetch_g2(client: Any, g2_url: str) -> list[dict[str, Any]]:
    run_input = {
        "mode": "product_reviews",
        "productUrls": [g2_url],
        "maxReviews": 10,
        "sortReviews": "rating_high",
        "minRating": 8,
    }
    run = _actor_call(client, G2_ACTOR, run_input)
    items = _dataset_items(client, run, named="reviews")
    return [row for row in items if isinstance(row, dict)]


def build_payload(
    *,
    query: str,
    brand: str,
    competitor: str | None,
    serp_items: list[dict[str, Any]],
    quotes: list[dict[str, Any]],
    source: str,
) -> dict[str, Any]:
    item = next((row for row in serp_items if isinstance(row, dict)), {}) or {}
    payload = normalize_serp_item(item, query)
    payload = attach_mentions(payload, brand, competitor)
    payload["quotes"] = quotes
    payload["source"] = source
    payload["fetched_at"] = datetime.now(timezone.utc).isoformat()
    payload["raw_item_count"] = len(serp_items)
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch GEO citation signals via Apify.")
    parser.add_argument("--query", required=True, help="Search query / head keyword")
    parser.add_argument("--brand", required=True, help="Brand to look for in AI citations")
    parser.add_argument("--competitor", default=None, help="Optional competitor name")
    parser.add_argument("--g2-url", default=None, help="Optional G2 product reviews URL")
    parser.add_argument("--country-code", default="us")
    parser.add_argument("--language-code", default="en")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Load fixtures instead of calling Apify",
    )
    parser.add_argument(
        "--fixture",
        default=None,
        help="Normalized or raw SERP JSON for --offline (default: skill fixtures/serp_sample.json)",
    )
    parser.add_argument(
        "--g2-fixture",
        default=None,
        help="Optional G2 reviews JSON for --offline",
    )
    parser.add_argument("--out", default=None, help="Also write JSON to this path")
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    quotes: list[dict[str, Any]] = []

    if args.offline:
        fixture_path = Path(args.fixture) if args.fixture else fixture_file("serp_sample.json")
        if args.fixture and not fixture_path.is_file():
            fixture_path = fixture_file(args.fixture)
        if not fixture_path.is_file():
            print(f"offline fixture not found: {fixture_path}", file=sys.stderr)
            return 1
        data = read_json(fixture_path)
        if isinstance(data, dict) and "ai_overview_text" in data:
            payload = dict(data)
            payload["query"] = args.query or payload.get("query")
            payload = attach_mentions(payload, args.brand, args.competitor)
            payload["source"] = payload.get("source") or "offline-normalized"
        else:
            items = data if isinstance(data, list) else [data]
            payload = build_payload(
                query=args.query,
                brand=args.brand,
                competitor=args.competitor,
                serp_items=items,
                quotes=[],
                source="offline-raw",
            )
        g2_path = Path(args.g2_fixture) if args.g2_fixture else fixture_file("g2_sample.json")
        if args.g2_fixture and not g2_path.is_file():
            g2_path = fixture_file(args.g2_fixture)
        if args.g2_url or args.g2_fixture or g2_path.is_file():
            if g2_path.is_file():
                reviews = read_json(g2_path)
                if isinstance(reviews, list):
                    quotes = quotes_for_brand(quotes_from_reviews(reviews), args.brand)
        payload["quotes"] = quotes
        if args.competitor is not None or "brand" not in payload:
            payload = attach_mentions(payload, args.brand, args.competitor)
    else:
        load_dotenv()
        token = __import__("os").environ.get("APIFY_TOKEN", "").strip()
        if not token:
            print("APIFY_TOKEN is required for live fetches. Use --offline or set .env.", file=sys.stderr)
            return 1
        try:
            from apify_client import ApifyClient
        except ImportError:
            req = skill_dir() / "requirements.txt"
            print(f"Install dependencies: python3 -m pip install -r {req}", file=sys.stderr)
            return 1
        client = ApifyClient(token)
        try:
            items = fetch_serp_live(client, args.query, args.country_code, args.language_code)
        except Exception as exc:  # noqa: BLE001 — surface Actor errors to the agent
            print(f"google-search-scraper failed: {exc}", file=sys.stderr)
            items = []
        payload = build_payload(
            query=args.query,
            brand=args.brand,
            competitor=args.competitor,
            serp_items=items,
            quotes=[],
            source="apify/google-search-scraper",
        )
        if not payload.get("ai_overview_text"):
            try:
                fallback_items = fetch_overview_fallback(client, args.query)
            except Exception as exc:  # noqa: BLE001
                print(f"google-ai-overviews-scraper fallback failed: {exc}", file=sys.stderr)
                fallback_items = []
            if fallback_items:
                payload = build_payload(
                    query=args.query,
                    brand=args.brand,
                    competitor=args.competitor,
                    serp_items=fallback_items,
                    quotes=[],
                    source="apify/google-ai-overviews-scraper",
                )
        if args.g2_url:
            try:
                reviews = fetch_g2(client, args.g2_url)
                quotes = quotes_for_brand(quotes_from_reviews(reviews), args.brand)
            except Exception as extra:  # noqa: BLE001
                print(f"G2 fetch skipped: {extra}", file=sys.stderr)
                quotes = []
            payload["quotes"] = quotes

    # Keep stdout JSON-only for the agent.
    if not payload.get("ai_overview_text"):
        payload["warning"] = "No AI Overview text returned for this query."

    rendered = write_json(payload)
    if args.out:
        out_path = __import__("pathlib").Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
