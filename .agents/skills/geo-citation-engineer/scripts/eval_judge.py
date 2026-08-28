#!/usr/bin/env python3
"""LLM-as-a-judge (RAG triad) with heuristic offline fallback."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from geo_compliance import evaluate as compliance_evaluate
from geo_lib import (
    body_sentences,
    extract_numbers,
    load_dotenv,
    read_json,
    section_named,
    write_json,
)

PASS_THRESHOLD = 0.7
JUDGE_SCHEMA_HINT = """
Return ONLY valid JSON with this exact shape:
{
  "rationale": "chain-of-thought that inspects claims before scoring",
  "scores": {
    "context_relevance": 0.0,
    "groundedness": 0.0,
    "answer_relevance": 0.0
  },
  "claims": [
    {"claim": "atomic claim", "supported": true, "evidence": "quote from source JSON or NONE"}
  ],
  "pass": true
}
Rules:
- Do not reward verbosity. Short, structured answers can score 1.0.
- Invented statistics or quotes that are absent from SOURCE_JSON must set groundedness to 0.0 and pass to false.
- context_relevance measures whether SOURCE_JSON addresses QUERY, not the rewrite quality.
- answer_relevance measures whether the rewrite follows GEO structure (atomic sentences, lists, sourced stats) and the GTM ask.
- Scores are floats in [0, 1].
""".strip()


def _blob(source: dict) -> str:
    parts = [
        str(source.get("query") or ""),
        str(source.get("ai_overview_text") or ""),
        json.dumps(source.get("cited_sources") or [], ensure_ascii=False),
        json.dumps(source.get("quotes") or [], ensure_ascii=False),
        json.dumps(source.get("fan_out") or [], ensure_ascii=False),
        str(source.get("gap") or ""),
    ]
    return "\n".join(parts)


def heuristic_judge(query: str, rewrite: str, source: dict) -> dict[str, Any]:
    scoped = section_named(rewrite, "Rewritten page") or rewrite
    source_blob = _blob(source)
    query_terms = {w.lower() for w in re.findall(r"[a-zA-Z0-9]+", query) if len(w) > 2}
    source_terms = {w.lower() for w in re.findall(r"[a-zA-Z0-9]+", source_blob) if len(w) > 2}
    overlap = len(query_terms & source_terms) / max(len(query_terms), 1)
    context = min(1.0, overlap / 0.5) if query_terms else 0.0

    source_numbers = extract_numbers(source_blob)
    rewrite_numbers = extract_numbers(scoped)
    invented = sorted(rewrite_numbers - source_numbers)
    claims = []
    for sentence in body_sentences(scoped)[:12]:
        nums = extract_numbers(sentence)
        unsupported_nums = nums - source_numbers
        supported = not unsupported_nums
        claims.append(
            {
                "claim": sentence,
                "supported": supported,
                "evidence": "number in SOURCE_JSON" if nums and supported else (
                    "NONE" if unsupported_nums else "qualitative; no invented number"
                ),
            }
        )
    groundedness = 0.0 if invented else (1.0 if claims else 0.0)
    if invented:
        groundedness = 0.0

    compliance = compliance_evaluate(rewrite, source)
    answer = compliance["geo_compliance_score"]
    if str(source.get("gap") or "").lower() not in rewrite.lower() and "gap" not in rewrite.lower():
        answer = min(answer, 0.6)

    scores = {
        "context_relevance": round(context, 3),
        "groundedness": round(groundedness, 3),
        "answer_relevance": round(float(answer), 3),
    }
    passed = (
        scores["context_relevance"] >= PASS_THRESHOLD
        and scores["groundedness"] >= PASS_THRESHOLD
        and scores["answer_relevance"] >= PASS_THRESHOLD
        and compliance["pass"]
        and not invented
    )
    rationale = (
        "Heuristic judge (no LLM key). "
        f"Query-source token overlap={overlap:.2f}. "
        f"Invented numbers={invented or 'none'}. "
        f"Compliance pass={compliance['pass']}."
    )
    return {
        "rationale": rationale,
        "scores": scores,
        "claims": claims,
        "pass": passed,
        "invented_numbers": invented,
        "geo_compliance": compliance,
    }


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise ValueError("judge did not return JSON")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("judge JSON was not an object")
    return data


def _validate_judge_payload(data: dict[str, Any]) -> dict[str, Any]:
    if "rationale" not in data or "scores" not in data:
        raise ValueError("judge JSON missing rationale or scores")
    scores = data["scores"]
    for key in ("context_relevance", "groundedness", "answer_relevance"):
        if key not in scores:
            raise ValueError(f"missing score {key}")
        scores[key] = float(scores[key])
    data["pass"] = bool(data.get("pass"))
    data["claims"] = data.get("claims") or []
    return data


def build_prompt(query: str, rewrite: str, source: dict, original: str | None, order_label: str) -> str:
    original_block = original or "(not provided)"
    return f"""You are an independent GEO auditor. Ignore length as a quality signal.

QUERY:
{query}

ORDER_LABEL: {order_label}

SOURCE_JSON:
{json.dumps(source, ensure_ascii=False, indent=2)[:12000]}

ORIGINAL_DRAFT:
{original_block[:4000]}

REWRITE:
{rewrite[:12000]}

{JUDGE_SCHEMA_HINT}
"""


def call_anthropic(prompt: str) -> str:
    from anthropic import Anthropic

    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
    client = Anthropic()
    message = client.messages.create(
        model=model,
        max_tokens=1200,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    chunks = []
    for block in message.content:
        text = getattr(block, "text", None)
        if text:
            chunks.append(text)
    return "\n".join(chunks)


def call_openai(prompt: str) -> str:
    from openai import OpenAI

    model = os.environ.get("OPENAI_JUDGE_MODEL", "gpt-4o")
    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content or ""


def _gemini_key() -> str:
    return (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()


def call_gemini(prompt: str) -> str:
    from google import genai
    from google.genai import types

    model = os.environ.get("GEMINI_JUDGE_MODEL", "gemini-2.5-flash")
    client = genai.Client(api_key=_gemini_key())
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
        ),
    )
    text = getattr(response, "text", None) or ""
    if not text:
        raise ValueError("Gemini returned an empty judge payload")
    return text


def select_judge_provider(explicit: str | None = None) -> str:
    """Pick a judge backend. Order: explicit flag, then Anthropic, Gemini, OpenAI."""
    if explicit and explicit != "auto":
        return explicit
    if os.environ.get("ANTHROPIC_API_KEY", "").strip():
        return "anthropic"
    if _gemini_key():
        return "gemini"
    if os.environ.get("OPENAI_API_KEY", "").strip():
        return "openai"
    return "heuristic"


def llm_judge(
    query: str,
    rewrite: str,
    source: dict,
    original: str | None,
    provider: str,
) -> tuple[str, dict[str, Any]]:
    callers = {
        "anthropic": call_anthropic,
        "gemini": call_gemini,
        "openai": call_openai,
    }
    if provider not in callers:
        raise ValueError(f"unknown judge provider: {provider}")
    caller = callers[provider]

    orders = [("rewrite_first", rewrite, original)]
    if original:
        orders.append(("original_first", original, rewrite))

    parsed_runs: list[dict[str, Any]] = []
    for label, primary, secondary in orders:
        if label == "original_first":
            prompt = build_prompt(query, primary, source, secondary, label)
        else:
            prompt = build_prompt(query, rewrite, source, original, label)
        raw = caller(prompt)
        parsed_runs.append(_validate_judge_payload(_extract_json(raw)))

    primary_result = parsed_runs[0]
    if len(parsed_runs) == 2:
        avg = {}
        for key in ("context_relevance", "groundedness", "answer_relevance"):
            avg[key] = round((parsed_runs[0]["scores"][key] + parsed_runs[1]["scores"][key]) / 2, 3)
        primary_result["scores"] = avg
        primary_result["pairwise"] = {
            "rewrite_first": parsed_runs[0]["scores"],
            "original_first": parsed_runs[1]["scores"],
            "average": avg,
        }
        primary_result["pass"] = all(v >= PASS_THRESHOLD for v in avg.values())
    return provider, primary_result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="RAG-triad judge for GEO rewrites.")
    parser.add_argument("--rewrite", required=True)
    parser.add_argument("--source", required=True, help="Fetcher JSON path")
    parser.add_argument("--query", required=True)
    parser.add_argument("--original-draft", default=None)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Skip paid LLM APIs and use the heuristic judge",
    )
    parser.add_argument(
        "--judge",
        choices=("auto", "anthropic", "gemini", "openai", "heuristic"),
        default="auto",
        help="Judge backend. auto = Anthropic, then Gemini, then OpenAI, else heuristic.",
    )
    parser.add_argument("--out", default=None)
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    rewrite_path = Path(args.rewrite)
    source_path = Path(args.source)
    if not rewrite_path.is_file() or not source_path.is_file():
        print("rewrite or source path missing", file=sys.stderr)
        return 1
    rewrite = rewrite_path.read_text(encoding="utf-8")
    source = read_json(source_path)
    if not isinstance(source, dict):
        print("source JSON must be an object", file=sys.stderr)
        return 1
    original = Path(args.original_draft).read_text(encoding="utf-8") if args.original_draft else None

    provider = "heuristic"
    try:
        if args.offline:
            chosen = "heuristic"
        else:
            chosen = select_judge_provider(args.judge)
        if chosen == "gemini" and not _gemini_key():
            print(
                "GEMINI_API_KEY is not set. Create a key at https://aistudio.google.com/api-keys",
                file=sys.stderr,
            )
            return 1
        if chosen in {"anthropic", "gemini", "openai"}:
            provider, judged = llm_judge(args.query, rewrite, source, original, chosen)
        else:
            judged = heuristic_judge(args.query, rewrite, source)
            provider = "heuristic"
    except Exception as exc:  # noqa: BLE001 — parse/API failure must not look like a pass
        print(f"judge harness error: {exc}", file=sys.stderr)
        payload = {
            "judge": "error",
            "pass": False,
            "error": str(exc),
            "rationale": "Judge output could not be parsed or the API call failed.",
        }
        sys.stdout.write(write_json(payload))
        return 1

    compliance = judged.get("geo_compliance") or compliance_evaluate(rewrite, source)
    payload = {
        "judge": provider,
        "rationale": judged.get("rationale"),
        "scores": judged.get("scores"),
        "claims": judged.get("claims") or [],
        "pass": bool(judged.get("pass")) and bool(compliance.get("pass")),
        "geo_compliance": compliance,
        "pairwise": judged.get("pairwise"),
        "invented_numbers": judged.get("invented_numbers") or [],
    }
    rendered = write_json(payload)
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if payload["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
