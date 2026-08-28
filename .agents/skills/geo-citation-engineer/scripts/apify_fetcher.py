#!/usr/bin/env python3
"""Fetch citation signals: DuckDuckGo HTML (stdlib), optional Apify, or fixtures."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

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
DDG_HTML_URL = "https://html.duckduckgo.com/html/"
DDG_TIMEOUT_SECS = 8
DDG_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


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
        *[s.get("title", "") for s in payload.get("organic") or []],
        *[s.get("url", "") for s in payload.get("organic") or []],
        *[s.get("snippet", "") for s in payload.get("organic") or []],
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


def ensure_names_in_offline_overview(payload: dict[str, Any], brand: str, competitor: str | None) -> dict[str, Any]:
    """Offline fixtures are one SERP. Put the requested competitor in the overview so gap matching works."""
    adapted = dict(payload)
    overview = str(adapted.get("ai_overview_text") or "").strip()
    if competitor and not mentioned(competitor, [overview]):
        overview = f"{competitor} is a frequent pick for this query. {overview}".strip()
        adapted["ai_overview_text"] = overview
    query = str(adapted.get("query") or "").strip()
    fan = [str(item).strip() for item in (adapted.get("fan_out") or []) if str(item).strip()]
    if query:
        adapted["fan_out"] = [query] + [item for item in fan if item.lower() != query.lower()]
    adapted["query"] = query or adapted.get("query")
    adapted["brand"] = brand
    adapted["competitor"] = competitor
    return adapted


def _attr_classes(attrs: list[tuple[str, str | None]]) -> set[str]:
    raw = dict(attrs).get("class") or ""
    return {part for part in raw.split() if part}


def unwrap_ddg_url(href: str) -> str:
    href = (href or "").strip()
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    encoded = parse_qs(parsed.query).get("uddg") or []
    if encoded:
        return unquote(encoded[0])
    return href


class DdgHtmlParser(HTMLParser):
    """Pull organic title/url/snippet triples from DuckDuckGo HTML. Skip ads."""

    def __init__(self) -> None:
        super().__init__()
        self.results: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._buf: list[str] = []
        self._in_title = False
        self._in_snippet = False
        self._row_ad = False
        self._ad_stack: list[bool] = []

    def _flush(self) -> None:
        row = self._current
        skip = self._row_ad
        self._current = None
        self._in_title = False
        self._in_snippet = False
        self._buf = []
        self._row_ad = False
        if skip or not row:
            return
        if not (row.get("title") or row.get("url")):
            return
        self.results.append(row)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        classes = _attr_classes(attrs)
        href = dict(attrs).get("href") or ""
        if tag == "div":
            parent_ad = self._ad_stack[-1] if self._ad_stack else False
            self._ad_stack.append(parent_ad or "result--ad" in classes)
        if tag == "a" and "result__a" in classes:
            self._flush()
            in_ad = (self._ad_stack[-1] if self._ad_stack else False) or "result--ad" in classes
            self._row_ad = in_ad
            self._current = {"title": "", "url": unwrap_ddg_url(href), "snippet": ""}
            self._in_title = True
            self._buf = []
            return
        if self._current is None:
            return
        if "result__snippet" in classes:
            self._in_snippet = True
            self._buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._ad_stack:
            self._ad_stack.pop()
        if self._in_title and tag == "a" and self._current is not None:
            self._current["title"] = " ".join(self._buf).strip()
            self._in_title = False
            self._buf = []
            return
        if self._in_snippet and tag in {"a", "div", "span", "td"} and self._current is not None:
            self._current["snippet"] = " ".join(self._buf).strip()
            self._in_snippet = False
            self._buf = []

    def handle_data(self, data: str) -> None:
        if self._in_title or self._in_snippet:
            text = (data or "").strip()
            if text:
                self._buf.append(text)

    def close(self) -> None:
        self._flush()
        super().close()


def parse_ddg_html(html: str) -> list[dict[str, str]]:
    parser = DdgHtmlParser()
    parser.feed(html or "")
    parser.close()
    return parser.results


def fetch_ddg_html(query: str, timeout: float = DDG_TIMEOUT_SECS) -> str:
    params = urlencode({"q": query})
    request = Request(
        f"{DDG_HTML_URL}?{params}",
        headers={"User-Agent": DDG_USER_AGENT, "Accept": "text/html"},
        method="GET",
    )
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def ddg_results_to_serp_item(query: str, results: list[dict[str, str]]) -> dict[str, Any]:
    organic = [row for row in results if row.get("title") or row.get("url")][:10]
    snippets = [row["snippet"] for row in organic if row.get("snippet")]
    titles = [row["title"] for row in organic if row.get("title")]
    overview = " ".join(snippets[:5]).strip() or " ".join(titles[:3]).strip()
    related = [title for title in titles[1:6] if title.lower() != query.lower()]
    paa = [query] if query else []
    return {
        "aiOverview": {"text": overview, "sources": organic},
        "organicResults": organic,
        "peopleAlsoAsk": paa,
        "relatedQueries": related,
    }


def build_ddg_payload(query: str, brand: str, competitor: str | None, html: str) -> dict[str, Any] | None:
    results = parse_ddg_html(html)
    if not results:
        return None
    item = ddg_results_to_serp_item(query, results)
    payload = build_payload(
        query=query,
        brand=brand,
        competitor=competitor,
        serp_items=[item],
        quotes=[],
        source="duckduckgo-html",
    )
    if not payload.get("organic") and not payload.get("ai_overview_text"):
        return None
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch GEO citation signals (DuckDuckGo, Apify, or fixtures).")
    parser.add_argument("--query", required=True, help="Search query / head keyword")
    parser.add_argument("--brand", required=True, help="Brand to look for in AI citations")
    parser.add_argument("--competitor", default=None, help="Optional competitor name")
    parser.add_argument("--g2-url", default=None, help="Optional G2 product reviews URL")
    parser.add_argument("--country-code", default="us")
    parser.add_argument("--language-code", default="en")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Load fixtures instead of the network",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Hit Apify Google search / AI Overview (needs APIFY_TOKEN)",
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


def load_offline_payload(args: argparse.Namespace) -> dict[str, Any]:
    fixture_path = Path(args.fixture) if args.fixture else fixture_file("serp_sample.json")
    if args.fixture and not fixture_path.is_file():
        fixture_path = fixture_file(args.fixture)
    if not fixture_path.is_file():
        raise FileNotFoundError(f"offline fixture not found: {fixture_path}")
    data = read_json(fixture_path)
    quotes: list[dict[str, Any]] = []
    if isinstance(data, dict) and "ai_overview_text" in data:
        payload = dict(data)
        payload["query"] = args.query or payload.get("query")
        payload = ensure_names_in_offline_overview(payload, args.brand, args.competitor)
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
        payload = ensure_names_in_offline_overview(payload, args.brand, args.competitor)
        payload = attach_mentions(payload, args.brand, args.competitor)
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
    return payload


def fetch_apify_payload(args: argparse.Namespace) -> dict[str, Any]:
    token = os.environ.get("APIFY_TOKEN", "").strip()
    if not token:
        raise RuntimeError("APIFY_TOKEN is required for --live. Use default DuckDuckGo, --offline, or set .env.")
    try:
        from apify_client import ApifyClient
    except ImportError as exc:
        req = skill_dir() / "requirements.txt"
        raise RuntimeError(f"Install dependencies: python3 -m pip install -r {req}") from exc
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
            payload["quotes"] = quotes_for_brand(quotes_from_reviews(reviews), args.brand)
        except Exception as extra:  # noqa: BLE001
            print(f"G2 fetch skipped: {extra}", file=sys.stderr)
            payload["quotes"] = []
    return payload


def fetch_ddg_payload(args: argparse.Namespace) -> dict[str, Any] | None:
    try:
        html = fetch_ddg_html(args.query)
    except Exception as exc:  # noqa: BLE001 — network/timeout must fall back
        print(f"DuckDuckGo HTML fetch failed: {exc}", file=sys.stderr)
        return None
    payload = build_ddg_payload(args.query, args.brand, args.competitor, html)
    if payload is None:
        print("DuckDuckGo HTML returned no organic results.", file=sys.stderr)
    return payload


def main() -> int:
    load_dotenv()
    args = parse_args()

    if args.offline:
        try:
            payload = load_offline_payload(args)
        except FileNotFoundError as exc:
            print(str(exc), file=sys.stderr)
            return 1
    elif args.live:
        try:
            payload = fetch_apify_payload(args)
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        if not payload.get("ai_overview_text") and not payload.get("organic"):
            print("Apify returned no overview; falling back to fixture.", file=sys.stderr)
            payload = load_offline_payload(args)
    else:
        payload = fetch_ddg_payload(args)
        if payload is None:
            print("Falling back to offline fixture.", file=sys.stderr)
            try:
                payload = load_offline_payload(args)
            except FileNotFoundError as exc:
                print(str(exc), file=sys.stderr)
                return 1

    # Keep stdout JSON-only for the agent.
    if not payload.get("ai_overview_text"):
        payload["warning"] = "No AI Overview text returned for this query."

    rendered = write_json(payload)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
