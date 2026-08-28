#!/usr/bin/env python3
"""Fetch Google AI Overview + optional G2 quotes; emit normalized GEO JSON."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from geo_lib import (
    clip_quote,
    gap_verdict,
    load_dotenv,
    mentioned,
    read_json,
    repo_root,
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


# Google appends interface chrome to the rendered AI Overview. Left in, it drags
# UI strings and their digits ("valid for seven days") into the evidence budget.
CHROME_MARKERS = (
    "AI responses may include mistakes",
    "AI can make mistakes",
    "Your feedback helps Google improve",
    "This public link is valid for",
    "About this responseSave to Google Drive",
    "When you export, you will allow Google Search",
    "Save to Google Drive",
)


def strip_overview_chrome(text: str) -> str:
    cut = len(text or "")
    for marker in CHROME_MARKERS:
        found = (text or "").find(marker)
        if found != -1:
            cut = min(cut, found)
    return (text or "")[:cut].strip()


def _publisher_slugs(title: str) -> list[str]:
    """Candidate publisher slugs from a SERP title.

    The publisher is usually the last ' - ' / ' | ' segment ("... - CrowdSpace")
    but sometimes the first ("BrikkApp | Invest in Real Estate"), so try every
    segment, longest first, plus the leading word.
    """
    parts = [p for p in re.split(r"\s*[-|·]\s*", title or "") if p.strip()]
    candidates = [parts[-1], parts[0]] if parts else []
    candidates += parts
    first_word = (parts[0].split() or [""])[0] if parts else ""
    candidates.append(first_word)
    slugs: list[str] = []
    for cand in candidates:
        slug = re.sub(r"[^a-z0-9]+", "", cand.lower())
        if len(slug) >= 4 and slug not in slugs:
            slugs.append(slug)
    return slugs


def resolve_cited_urls(
    cited: list[dict[str, str]], organic: list[dict[str, str]]
) -> list[dict[str, str]]:
    """Replace Google /goto redirect stubs with the real publisher URL.

    The AI Overview block returns opaque redirect URLs. An unresolvable citation
    URL is worthless as evidence, so match the citation's publisher against the
    organic results, which do carry real URLs. Anything unmatched is flagged
    rather than silently kept as a stub.
    """
    domains = []
    for row in organic:
        match = re.match(r"https?://([^/]+)", row.get("url", "") or "")
        if match:
            domains.append((re.sub(r"[^a-z0-9]+", "", match.group(1).lower()), row["url"]))

    out: list[dict[str, str]] = []
    for row in cited:
        record = dict(row)
        url = record.get("url", "") or ""
        if url.startswith("http"):
            out.append(record)
            continue
        record["url_raw"] = url
        hit = ""
        for slug in _publisher_slugs(record.get("title", "")):
            hit = next((full for dom, full in domains if slug in dom), "")
            if hit:
                break
        if hit:
            record["url"] = hit
            record["url_resolved_from"] = "organic_publisher_match"
        else:
            record["url"] = ""
            record["url_note"] = "Google redirect stub; publisher URL not resolvable from this capture"
        out.append(record)
    return out


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

    unique_related: list[str] = []
    for row in related:
        if row not in unique_related:
            unique_related.append(row)
    related = unique_related

    return {
        "query": query,
        "ai_overview_text": strip_overview_chrome(ai_text),
        "cited_sources": resolve_cited_urls(cited, organic),
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


def _as_dict(run: Any) -> dict[str, Any]:
    """apify-client 2.x returns a dict; 3.x returns a typed Run object."""
    if run is None:
        return {}
    if isinstance(run, dict):
        return run
    for attr in ("model_dump", "dict", "_asdict"):
        fn = getattr(run, attr, None)
        if callable(fn):
            try:
                out = fn()
                if isinstance(out, dict):
                    return out
            except Exception:  # noqa: BLE001 — fall through to attribute scrape
                pass
    return {
        key: getattr(run, key)
        for key in dir(run)
        if not key.startswith("_") and not callable(getattr(run, key, None))
    }


def _actor_call(client: Any, actor_id: str, run_input: dict[str, Any]) -> dict[str, Any]:
    """Call an Actor across apify-client 2.x and 3.x.

    3.x renamed timeout_secs/wait_secs to run_timeout/wait_duration (timedelta)
    and defaults logger='default', which streams Actor logs to stdout and would
    corrupt this script's JSON-only stdout contract.
    """
    actor = client.actor(actor_id)
    wait = timedelta(seconds=DEFAULT_WAIT_SECS)
    attempts: list[dict[str, Any]] = [
        {"run_input": run_input, "run_timeout": wait, "wait_duration": wait, "logger": None},
        {"run_input": run_input, "timeout_secs": DEFAULT_WAIT_SECS, "wait_secs": DEFAULT_WAIT_SECS},
        {"run_input": run_input},
    ]
    last_error: Exception | None = None
    for kwargs in attempts:
        try:
            return _as_dict(actor.call(**kwargs))
        except TypeError as exc:  # unsupported kwarg for this client version
            last_error = exc
            continue
    raise last_error or RuntimeError("actor call failed")


def _dataset_items(client: Any, run: dict[str, Any], named: str | None = None) -> list[dict[str, Any]]:
    dataset_id = None
    run = _as_dict(run)
    storage = _as_dict(run.get("storageIds") or run.get("storage_ids") or {})
    datasets = _as_dict(storage.get("datasets") or {})
    if named and datasets.get(named):
        dataset_id = datasets[named]
    dataset_id = dataset_id or run.get("defaultDatasetId") or run.get("default_dataset_id")
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
        help=(
            "Normalized or raw SERP JSON for --offline "
            "(default: demo/input/snapshots/best-bible-study-app.2026-08-28.json)"
        ),
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
    root = repo_root()
    quotes: list[dict[str, Any]] = []

    if args.offline:
        # Default to real captured evidence, not the synthetic unit-test fixture.
        fixture_path = root / (
            args.fixture or "demo/input/snapshots/best-bible-study-app.2026-08-28.json"
        )
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
        # Only ever load a G2 fixture that was asked for by name. Auto-loading a
        # default would splice synthetic review quotes into a real capture.
        if args.g2_fixture:
            g2_path = root / args.g2_fixture
            if not g2_path.is_file():
                print(f"g2 fixture not found: {g2_path}", file=sys.stderr)
                return 1
            reviews = read_json(g2_path)
            if isinstance(reviews, list):
                quotes = quotes_from_reviews(reviews)
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
            print("Install dependencies: pip install -r requirements.txt", file=sys.stderr)
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
                quotes = quotes_from_reviews(reviews)
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
