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
- Score DOCUMENT_TO_SCORE only. ORIGINAL_DRAFT is background. Do not blend the two into one score.
- Do not reward verbosity. Short, structured answers can score 1.0.
- Do not use 0.5 as a hedge. Pick high (>= 0.9) or low (<= 0.3) unless the evidence is truly mixed.
- If every listed claim is supported by SOURCE_JSON, groundedness MUST be >= 0.9.
- Invented statistics or quotes absent from SOURCE_JSON => groundedness 0.0 and pass false.
- context_relevance: does SOURCE_JSON address QUERY (not rewrite quality).
- answer_relevance: does DOCUMENT_TO_SCORE follow GEO structure (atomic sentences, lists, sourced stats) and the GTM ask.
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


def build_prompt(query: str, rewrite: str, source: dict, original: str | None) -> str:
    original_block = original or "(not provided)"
    return f"""You are an independent GEO auditor. Ignore length as a quality signal.

QUERY:
{query}

SOURCE_JSON:
{json.dumps(source, ensure_ascii=False, indent=2)[:12000]}

ORIGINAL_DRAFT (do not score this document):
{original_block[:4000]}

DOCUMENT_TO_SCORE (the GEO rewrite — score this only):
{rewrite[:12000]}

{JUDGE_SCHEMA_HINT}
"""


def calibrate_scores(payload: dict[str, Any]) -> dict[str, Any]:
    """Keep LLM scores, but stop midpoint hedges when claims are unanimous."""
    claims = payload.get("claims") or []
    scores = dict(payload.get("scores") or {})
    for key in ("context_relevance", "groundedness", "answer_relevance"):
        scores[key] = float(scores.get(key) or 0.0)
    if claims:
        if all(bool(claim.get("supported")) for claim in claims):
            scores["groundedness"] = max(scores["groundedness"], 0.9)
        if any(not claim.get("supported") for claim in claims):
            scores["groundedness"] = 0.0
    payload["scores"] = scores
    payload["pass"] = all(scores[key] >= PASS_THRESHOLD for key in scores)
    return payload


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


DEFAULT_GEMINI_MODELS = (
    "gemini-3.6-flash",
    "gemini-3-flash",
    "gemini-flash-latest",
)


def _gemini_models() -> list[str]:
    preferred = (os.environ.get("GEMINI_JUDGE_MODEL") or "").strip()
    models: list[str] = []
    for name in (preferred, *DEFAULT_GEMINI_MODELS):
        if name and name not in models:
            models.append(name)
    return models


def _gemini_text_from_response(response: object) -> str:
    text = getattr(response, "text", None) or getattr(response, "output_text", None) or ""
    return text if isinstance(text, str) else ""


def call_gemini(prompt: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=_gemini_key())
    config_kwargs: dict = {
        "temperature": 0,
        "response_mime_type": "application/json",
    }
    afc = getattr(types, "AutomaticFunctionCallingConfig", None)
    if afc is not None:
        config_kwargs["automatic_function_calling"] = afc(disable=True)

    errors: list[str] = []
    for model in _gemini_models():
        try:
            interactions = getattr(client, "interactions", None)
            create = getattr(interactions, "create", None) if interactions else None
            if callable(create):
                response = create(model=model, input=prompt)
            else:
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
            text = _gemini_text_from_response(response)
            if not text:
                raise ValueError("Gemini returned an empty judge payload")
            return text
        except Exception as exc:  # noqa: BLE001 — try the next model on 404s
            message = str(exc)
            errors.append(f"{model}: {message}")
            if "NOT_FOUND" not in message and "404" not in message:
                raise
    raise ValueError("Gemini judge failed for all models. " + " | ".join(errors))


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
    prompt = build_prompt(query, rewrite, source, original)
    raw = caller(prompt)
    primary_result = calibrate_scores(_validate_judge_payload(_extract_json(raw)))
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
    judged = calibrate_scores(judged)
    scores = dict(judged.get("scores") or {})
    if compliance.get("pass"):
        scores["answer_relevance"] = max(
            float(scores.get("answer_relevance") or 0),
            float(compliance.get("geo_compliance_score") or 0),
        )
    judged["scores"] = scores
    judged["pass"] = all(float(scores.get(key) or 0) >= PASS_THRESHOLD for key in (
        "context_relevance",
        "groundedness",
        "answer_relevance",
    ))
    payload = {
        "judge": provider,
        "rationale": judged.get("rationale"),
        "scores": scores,
        "claims": judged.get("claims") or [],
        "pass": bool(judged.get("pass")) and bool(compliance.get("pass")),
        "geo_compliance": compliance,
        "pairwise": None,
        "invented_numbers": judged.get("invented_numbers") or [],
    }
    rendered = write_json(payload)
    if args.out:
        Path(args.out).write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0 if payload["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
