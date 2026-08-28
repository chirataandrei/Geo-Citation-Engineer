#!/usr/bin/env python3
"""One-call GEO orchestrator: plan a rewrite from a brief, then score it.

Two modes, one command each. Everything deterministic happens here so the agent
only has to write prose once.

    run_geo.py plan  --brief demo/input/<case>.brief.json
    run_geo.py score --brief demo/input/<case>.brief.json

`plan` reads the brief and its evidence snapshot, computes the citation gap,
decides whether a rewrite is even warranted, writes a report scaffold with an
AGENT-REWRITE marker, and prints the only facts the agent is allowed to use.

`score` re-reads that report, refuses to pass while the marker is still there,
and runs deterministic compliance plus the offline heuristic judge.

No network. No credentials. Runs in well under a second.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_judge import heuristic_judge
from geo_compliance import TARGET_MAX_WORDS, evaluate
from geo_lib import (
    extract_numbers,
    gap_verdict,
    mentioned,
    read_json,
    repo_root,
    write_json,
)

MARKER = "<!-- AGENT-REWRITE: replace this block. See constraints printed by run_geo.py plan. -->"

CONSTRAINTS = [
    f"One fact per sentence. Every sentence <= {TARGET_MAX_WORDS} words. Hard fail over 18.",
    "Include at least one bullet list inside '## Rewritten page'.",
    "Digits: use ONLY values listed in allowed_numbers.all. Any other digit fails the eval.",
    "allowed_numbers.brand may be asserted about the brand.",
    "allowed_numbers.evidence belongs to third parties. Quote it ONLY with the source named "
    "in the same sentence. Never restate a competitor's rating or download count as the brand's.",
    "Write an H3 (###) for each question in fan_out_priority, inside '## Rewritten page'.",
    "Lead each section with the answer, then the support. No preamble.",
    "Name the competitor factually where the evidence supports it. Never disparage.",
    "Invent nothing: no statistic, quote, award, or customer count outside allowed_*.",
]


# --------------------------------------------------------------------------- #
# evidence assembly
# --------------------------------------------------------------------------- #

def resolve(root: Path, rel: str) -> Path:
    path = Path(rel)
    return path if path.is_absolute() else root / rel


def build_evidence(brief: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Merge snapshot + brief into the single JSON the evals score against."""
    evidence = dict(snapshot)
    brand = brief.get("brand") or ""
    competitor = brief.get("competitor") or None

    paa = list(evidence.get("people_also_ask") or [])
    related = list(evidence.get("related_queries") or [])
    fan_out: list[str] = []
    seen: set[str] = set()
    for item in paa + related:
        key = item.lower().strip()
        if key and key not in seen:
            seen.add(key)
            fan_out.append(item)
    evidence["fan_out"] = fan_out

    haystacks = [evidence.get("ai_overview_text") or ""]
    for row in (evidence.get("cited_sources") or []) + (evidence.get("organic") or []):
        haystacks += [row.get("title", ""), row.get("url", ""), row.get("snippet", "")]

    brand_hit = mentioned(brand, haystacks)
    competitor_hit = mentioned(competitor or "", haystacks) if competitor else False

    evidence["brand"] = brand
    evidence["competitor"] = competitor
    evidence["brand_mentioned_in_ai"] = brand_hit
    evidence["competitor_mentioned_in_ai"] = competitor_hit
    evidence["gap"] = gap_verdict(brand, competitor, brand_hit, competitor_hit)
    evidence["brand_facts"] = brief.get("brand_facts") or {"claims": []}
    return evidence


def citing_sources(evidence: dict[str, Any], name: str) -> list[dict[str, str]]:
    """Sources whose title/snippet/url actually name `name`."""
    if not name:
        return []
    hits = []
    for row in (evidence.get("cited_sources") or []):
        blob = [row.get("title", ""), row.get("url", ""), row.get("snippet", "")]
        if mentioned(name, blob):
            hits.append(row)
    return hits


def _sorted_numbers(values: set[str]) -> list[str]:
    return sorted(values, key=lambda s: (len(s), s))


def allowed_facts(evidence: dict[str, Any]) -> dict[str, list[str]]:
    """Split the fact budget by who is allowed to claim what.

    brand numbers come from first-party brand_facts and may be asserted about the
    brand. evidence numbers come from third-party SERP text; they are quotable
    only when attributed to the source that published them. Collapsing these two
    into one list is how a rewrite ends up claiming a competitor's star rating.
    """
    claims = list((evidence.get("brand_facts") or {}).get("claims") or [])
    brand_numbers = extract_numbers(" ".join(claims))

    evidence_parts = [
        evidence.get("ai_overview_text") or "",
        " ".join(evidence.get("fan_out") or []),
    ]
    for row in (evidence.get("cited_sources") or []) + (evidence.get("organic") or []):
        evidence_parts += [row.get("title", ""), row.get("snippet", "")]
    evidence_numbers = extract_numbers(" ".join(evidence_parts)) - brand_numbers

    return {
        "claims": claims,
        "brand_numbers": _sorted_numbers(brand_numbers),
        "evidence_numbers": _sorted_numbers(evidence_numbers),
        "all_numbers": _sorted_numbers(brand_numbers | evidence_numbers),
    }


def rank_fan_out(query: str, fan_out: list[str], limit: int = 3) -> list[str]:
    """Rank fan-out questions by token overlap with the head query.

    The captured People-Also-Ask block contains genuine but off-topic questions.
    Writing an H3 for each of nine items also blows the 75s demo budget, so the
    agent is handed a short priority list and the full set stays in the report.
    """
    stop = {"the", "a", "an", "is", "for", "of", "to", "what", "best", "app", "and", "in", "with"}
    q_tokens = {t for t in re.findall(r"[a-z0-9]+", query.lower()) if t not in stop}

    def score(item: str) -> tuple[int, int]:
        tokens = {t for t in re.findall(r"[a-z0-9]+", item.lower()) if t not in stop}
        return (len(q_tokens & tokens), -len(item))

    ranked = sorted(fan_out, key=score, reverse=True)

    # Captured fan-out is full of near-duplicates ("best crm for startups free" vs
    # "free CRM for startups"). Writing an H3 for each wastes the demo budget on
    # the same answer three times, so collapse by content-word set.
    deduped: list[str] = []
    seen: list[set[str]] = []
    for item in ranked:
        tokens = {t for t in re.findall(r"[a-z0-9]+", item.lower()) if t not in stop}
        if any(tokens and tokens == prev for prev in seen):
            continue
        seen.append(tokens)
        deduped.append(item)

    on_topic = [item for item in deduped if score(item)[0] > 0]
    return (on_topic or deduped)[:limit]


def classify(evidence: dict[str, Any], numbers: list[str]) -> dict[str, str]:
    """Decide whether to rewrite, degrade, or decline. This is the exclusion gate."""
    cited = evidence.get("cited_sources") or []
    has_overview = bool(evidence.get("ai_overview_text"))

    if not has_overview and len(cited) < 2:
        return {
            "evidence_level": "insufficient",
            "opportunity": "none",
            "action": "abort",
            "reason": (
                f"Only {len(cited)} cited source(s) and no AI Overview text. "
                "Not enough evidence to claim a citation gap. Report and stop."
            ),
        }

    if evidence.get("brand_mentioned_in_ai"):
        verdict = evidence.get("gap") or ""
        return {
            "evidence_level": "sufficient",
            "opportunity": "none",
            "action": "decline",
            "reason": (
                f"Brand is already inside the citable set ({verdict}). "
                "There is no citation gap to close, so no rewrite is warranted."
            ),
        }

    # Competitor named vs nobody named are different opportunities and deserve
    # different copy: one displaces an incumbent answer, the other claims a
    # question no one owns yet.
    contested = bool(evidence.get("competitor_mentioned_in_ai"))
    opportunity = "competitor_gap" if contested else "uncontested_answer"
    framing = (
        f"{evidence.get('competitor')} is named in the AI Overview and {evidence.get('brand')} is not. "
        "Displace the incumbent answer."
        if contested
        else (
            f"Neither {evidence.get('brand')} nor {evidence.get('competitor')} is named in the AI "
            "Overview. This answer is unclaimed — write to own it rather than to displace anyone."
        )
    )

    if not numbers:
        return {
            "evidence_level": "qualitative_only",
            "opportunity": opportunity,
            "action": "rewrite",
            "reason": f"{framing} No numeric facts available, so write qualitative atomic facts only.",
        }

    return {
        "evidence_level": "sufficient",
        "opportunity": opportunity,
        "action": "rewrite",
        "reason": f"{framing} Numeric facts are available.",
    }


# --------------------------------------------------------------------------- #
# report scaffold
# --------------------------------------------------------------------------- #

def render_report(brief: dict[str, Any], evidence: dict[str, Any], verdict: dict[str, str]) -> str:
    prov = evidence.get("provenance") or {}
    brand = evidence.get("brand") or ""
    competitor = evidence.get("competitor") or "(none given)"
    comp_hits = citing_sources(evidence, competitor) if evidence.get("competitor") else []

    lines: list[str] = []
    add = lines.append

    add(f"# GEO citation gap: “{evidence.get('query','')}”")
    add("")
    add(f"- **Brand:** {brand}" + (f" ({brief.get('brand_domain')})" if brief.get("brand_domain") else ""))
    add(f"- **Competitor tracked:** {competitor}")
    add(f"- **Verdict:** {evidence.get('gap','')}")
    add(f"- **{competitor} named in the AI Overview:** {bool(evidence.get('competitor_mentioned_in_ai'))}")
    add(f"- **{brand} named in the AI Overview:** {bool(evidence.get('brand_mentioned_in_ai'))}")
    add(f"- **Evidence level:** {verdict['evidence_level']}")
    if verdict.get("opportunity") and verdict["opportunity"] != "none":
        add(f"- **Opportunity:** {verdict['opportunity'].replace('_',' ')}")
    add("")
    add("## Provenance")
    add("")
    add(f"- Source: `{prov.get('engine') or prov.get('method')}`")
    if prov.get("request_url"):
        add(f"- Request URL: {prov['request_url']}")
    add(f"- Retrieved at: {prov.get('retrieved_at') or 'n/a (test fixture)'}")
    add(f"- AI Overview rendered: {prov.get('ai_overview_present')}")
    if prov.get("ai_overview_note"):
        add(f"- Note: {prov['ai_overview_note']}")
    add("")
    add("## Who the engine already cites")
    add("")
    cited = evidence.get("cited_sources") or []
    if cited:
        add("| # | Source | URL | Names competitor |")
        add("|---|--------|-----|------------------|")
        for i, row in enumerate(cited, 1):
            names = "yes" if row in comp_hits else "no"
            add(f"| {i} | {row.get('title','')} | {row.get('url','')} | {names} |")
    else:
        add("_No cited sources captured._")
    add("")
    add(f"- Sources naming **{competitor}**: {len(comp_hits)} of {len(cited)}")
    add(f"- Sources naming **{brand}**: {len(citing_sources(evidence, brand))} of {len(cited)}")
    add("")
    add("## Fan-out questions captured")
    add("")
    fan_out = evidence.get("fan_out") or []
    priority = set(rank_fan_out(evidence.get("query") or "", fan_out))
    for item in fan_out:
        add(f"- {item}" + ("  ← covered below" if item in priority else ""))
    if not fan_out:
        add("_None captured._")
    add("")

    if verdict["action"] != "rewrite":
        add(f"## Outcome: no rewrite ({verdict['action']})")
        add("")
        add(verdict["reason"])
        add("")
        return "\n".join(lines) + "\n"

    add("## Rewritten page")
    add("")
    add(MARKER)
    add("")
    add("## Change log")
    add("")
    add("| Injection | Justified by |")
    add("|-----------|--------------|")
    add("| _fill after rewrite_ | _evidence field_ |")
    add("")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# modes
# --------------------------------------------------------------------------- #

def load_case(root: Path, brief_path: str) -> tuple[dict[str, Any], dict[str, Any], Path]:
    bpath = resolve(root, brief_path)
    if not bpath.is_file():
        raise SystemExit(f"brief not found: {bpath}")
    brief = read_json(bpath)
    snap = resolve(root, brief["snapshot"])
    if not snap.is_file():
        raise SystemExit(f"snapshot not found: {snap}")
    return brief, build_evidence(brief, read_json(snap)), bpath


def do_plan(root: Path, args: argparse.Namespace) -> int:
    brief, evidence, _ = load_case(root, args.brief)
    facts = allowed_facts(evidence)
    verdict = classify(evidence, facts["all_numbers"])

    out_dir = resolve(root, args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    case = brief.get("case_id") or "case"
    report_path = out_dir / f"geo-report.{case}.md"
    evidence_path = out_dir / f"evidence.{case}.json"

    report_path.write_text(render_report(brief, evidence, verdict), encoding="utf-8")
    evidence_path.write_text(write_json(evidence), encoding="utf-8")

    summary = {
        "case_id": case,
        "query": evidence.get("query"),
        "brand": evidence.get("brand"),
        "competitor": evidence.get("competitor"),
        "gap_verdict": evidence.get("gap"),
        "competitor_named_in_ai_overview": bool(evidence.get("competitor_mentioned_in_ai")),
        "brand_named_in_ai_overview": bool(evidence.get("brand_mentioned_in_ai")),
        "ai_overview_present": bool(evidence.get("ai_overview_text")),
        "evidence_level": verdict["evidence_level"],
        "opportunity": verdict.get("opportunity"),
        "action": verdict["action"],
        "reason": verdict["reason"],
        "report_path": str(report_path.relative_to(root)).replace("\\", "/"),
        "evidence_path": str(evidence_path.relative_to(root)).replace("\\", "/"),
        "draft_path": brief.get("draft"),
        "sources_naming_competitor": len(citing_sources(evidence, evidence.get("competitor") or "")),
        "sources_total": len(evidence.get("cited_sources") or []),
        "fan_out_priority": rank_fan_out(evidence.get("query") or "", evidence.get("fan_out") or []),
        "fan_out_all": evidence.get("fan_out") or [],
        "allowed_numbers": {
            "brand": facts["brand_numbers"],
            "evidence": facts["evidence_numbers"],
            "all": facts["all_numbers"],
        },
        "allowed_claims": facts["claims"],
        "constraints": CONSTRAINTS if verdict["action"] == "rewrite" else [],
        "next_step": (
            f"Replace the AGENT-REWRITE marker in {report_path.name} with the rewritten page, "
            "fill the change log, then run: run_geo.py score --brief " + args.brief
        )
        if verdict["action"] == "rewrite"
        else f"Stop. Report the {verdict['action']} outcome to the user. Do not rewrite.",
    }
    sys.stdout.write(write_json(summary))
    return 0


def do_score(root: Path, args: argparse.Namespace) -> int:
    brief, evidence, _ = load_case(root, args.brief)
    case = brief.get("case_id") or "case"
    out_dir = resolve(root, args.out_dir)
    report_path = out_dir / f"geo-report.{case}.md"
    if not report_path.is_file():
        print(f"report not found, run plan first: {report_path}", file=sys.stderr)
        return 1
    report = report_path.read_text(encoding="utf-8")

    verdict = classify(evidence, allowed_facts(evidence)["all_numbers"])

    if verdict["action"] != "rewrite":
        sys.stdout.write(
            write_json(
                {
                    "case_id": case,
                    "action": verdict["action"],
                    "reason": verdict["reason"],
                    "scored": False,
                    "pass": True,
                    "note": "Correctly declined to rewrite; nothing to score.",
                }
            )
        )
        return 0

    if MARKER in report:
        print(
            "AGENT-REWRITE marker is still in the report. Write the rewrite before scoring.",
            file=sys.stderr,
        )
        return 1

    draft = None
    if brief.get("draft"):
        dpath = resolve(root, brief["draft"])
        if dpath.is_file():
            draft = dpath.read_text(encoding="utf-8")

    compliance = evaluate(report, evidence)
    judged = heuristic_judge(evidence.get("query") or "", report, evidence)

    # Keep stdout small: the agent has a 75s budget and does not need the full
    # check dumps, only the verdict and anything that failed.
    result = {
        "case_id": case,
        "action": "rewrite",
        "scored": True,
        "geo_compliance": {
            "score": compliance["geo_compliance_score"],
            "pass": compliance["pass"],
            "sentence_count": compliance["sentence_count"],
            "within_15_words": f"{compliance['target_length_ratio']:.0%}",
            "checks": {c["name"]: ("pass" if c["pass"] else f"FAIL — {c['detail']}") for c in compliance["checks"]},
        },
        "judge": {
            "provider": "heuristic-offline",
            "scores": judged["scores"],
            "pass": judged["pass"],
            "invented_numbers": judged["invented_numbers"],
            "unsupported_claims": [c["claim"] for c in judged["claims"] if not c["supported"]],
        },
        "draft_words": len((draft or "").split()) if draft else None,
        "rewrite_words": len(report.split()),
        "pass": bool(compliance["pass"] and judged["pass"]),
    }
    sys.stdout.write(write_json(result))
    return 0 if result["pass"] else 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan and score a GEO rewrite from a brief.")
    parser.add_argument("mode", choices=["plan", "score"])
    parser.add_argument("--brief", required=True, help="Path to a *.brief.json")
    parser.add_argument(
        "--out-dir",
        default="output",
        help=(
            "Where reports are written. Defaults to the gitignored working dir so a live "
            "run never overwrites the committed fallback in demo/output/."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = repo_root()
    return do_plan(root, args) if args.mode == "plan" else do_score(root, args)


if __name__ == "__main__":
    raise SystemExit(main())
