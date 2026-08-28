#!/usr/bin/env python3
"""Stage demo: citation gap → GEO rewrite → eval scorecard. One command."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / ".agents" / "skills" / "geo-citation-engineer" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eval_judge import select_judge_provider  # noqa: E402
from geo_lib import load_dotenv, section_named  # noqa: E402

QUERY = "best crm for startups"
BRAND = "Acme"
COMPETITOR = "HubSpot"


def _tty() -> bool:
    return sys.stdout.isatty()


def _c(code: str, text: str) -> str:
    if not _tty():
        return text
    return f"\033[{code}m{text}\033[0m"


def bold(text: str) -> str:
    return _c("1", text)


def green(text: str) -> str:
    return _c("32", text)


def red(text: str) -> str:
    return _c("31", text)


def dim(text: str) -> str:
    return _c("2", text)


def cyan(text: str) -> str:
    return _c("36", text)


def rule(title: str) -> None:
    line = f"── {title} " + "─" * max(8, 52 - len(title))
    print()
    print(bold(line))
    print()


def wait(auto: bool) -> None:
    if auto:
        time.sleep(0.45)
        return
    try:
        input(dim("  [Enter] next beat  "))
    except EOFError:
        pass


def run_script(name: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    python = sys.executable
    return subprocess.run(
        [python, str(SCRIPTS / name), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def excerpt(text: str, limit: int = 420) -> str:
    compact = "\n".join(line.rstrip() for line in text.strip().splitlines() if line.strip())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def print_banner() -> None:
    print()
    print(bold("╔══════════════════════════════════════════════════════╗"))
    print(bold("║   GEO Citation Engineer · 2:30 live demo             ║"))
    print(bold("╚══════════════════════════════════════════════════════╝"))
    print()
    print(f"  {dim('query')}      {QUERY}")
    print(f"  {dim('brand')}      {BRAND}")
    print(f"  {dim('competitor')} {COMPETITOR}")
    print()
    print(dim("  Job: make first-party pages get cited in AI Overviews."))


def beat_draft(auto: bool) -> None:
    rule("1 / Losing page — current GTM copy")
    draft = (ROOT / "fixtures" / "draft.md").read_text(encoding="utf-8")
    print(dim(excerpt(draft, 520)))
    print()
    print(red("  No numbers. No citations. Sentences too long to be quoted."))
    wait(auto)


def beat_fetch(auto: bool, live: bool) -> dict:
    rule("2 / What AI search actually cites")
    out = ROOT / "output" / "serp.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "--query",
        QUERY,
        "--brand",
        BRAND,
        "--competitor",
        COMPETITOR,
        "--out",
        str(out),
    ]
    mode = "live Apify"
    if not live:
        cmd.insert(0, "--offline")
        mode = "offline fixture (same JSON contract as Apify)"
    print(dim(f"  sensor: apify_fetcher.py  ·  {mode}"))
    proc = run_script("apify_fetcher.py", cmd)
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout)
        if live:
            print(dim("  Live fetch failed — falling back to --offline."))
            return beat_fetch(auto, live=False)
        raise SystemExit(proc.returncode)
    payload = json.loads(out.read_text(encoding="utf-8"))
    overview = (payload.get("ai_overview_text") or "").strip()
    print()
    print(cyan("  AI Overview"))
    print(f"  {excerpt(overview, 280)}")
    print()
    gap = payload.get("gap") or "?"
    brand_hit = payload.get("brand_mentioned_in_ai")
    competitor_hit = payload.get("competitor_mentioned_in_ai")
    print(f"  {bold('GAP')}           {red(gap) if 'absent' in str(gap) else green(str(gap))}")
    print(f"  {dim('Acme cited?')}     {brand_hit}")
    print(f"  {dim('HubSpot cited?')}  {competitor_hit}")
    fan = payload.get("fan_out") or []
    if fan:
        print()
        print(dim("  fan-out (what the model actually retrieves)"))
        for item in fan[:4]:
            print(f"    · {item}")
    wait(auto)
    return payload


def beat_rewrite(auto: bool) -> None:
    rule("3 / Page engineered to get cited")
    rewrite = (ROOT / "fixtures" / "rewrite.md").read_text(encoding="utf-8")
    body = section_named(rewrite, "Rewritten page") or rewrite
    print(excerpt(body, 700))
    print()
    print(green("  Atomic sentences. Sourced 64%. List. G2 quote. Fan-out H2s."))
    wait(auto)


def beat_eval(auto: bool, judge: str) -> dict:
    rule("4 / Evals prove it works")
    args = [
        "--query",
        QUERY,
        "--rewrite",
        str(ROOT / "fixtures" / "rewrite.md"),
        "--source",
        str(ROOT / "output" / "serp.json"),
        "--original-draft",
        str(ROOT / "fixtures" / "draft.md"),
        "--judge",
        judge,
    ]
    print(dim(f"  judge: {judge}"))
    proc = run_script("eval_judge.py", args)
    raw = (proc.stdout or "").strip()
    if not raw:
        print(proc.stderr)
        raise SystemExit(proc.returncode or 1)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        print(raw)
        print(proc.stderr)
        raise SystemExit(1)
    scores = result.get("scores") or {}
    compliance = result.get("geo_compliance") or {}
    passed = bool(result.get("pass"))
    print()
    print(f"  {'metric':<22} {'score':<8} {'bar'}")
    print(dim("  " + "-" * 44))
    rows = [
        ("context relevance", scores.get("context_relevance")),
        ("groundedness", scores.get("groundedness")),
        ("answer relevance", scores.get("answer_relevance")),
        ("GEO compliance", compliance.get("geo_compliance_score")),
    ]
    for name, value in rows:
        try:
            num = float(value)
        except (TypeError, ValueError):
            num = 0.0
        filled = round(num * 10)
        bar = ("█" * filled) + ("░" * (10 - filled))
        print(f"  {name:<22} {num:<8.2f} {bar}")
    print()
    stamp = green("PASS") if passed else red("FAIL")
    print(f"  {bold('verdict')}   {stamp}   judge={result.get('judge')}   exit={proc.returncode}")
    wait(auto)
    return result


def beat_close(passed: bool) -> None:
    rule("Close")
    print("  A GTM job is now a portable Agent Skill:")
    print(f"    {cyan('$geo-citation-engineer')}")
    print("  MIT · fork into Codex / Claude Code · evals travel with the skill.")
    print()
    if passed:
        print(green("  Ready for the 2.5-minute slot."))
    else:
        print(red("  Eval failed — rerun with --judge heuristic if the LLM key misfired."))
    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GEO Citation Engineer stage demo.")
    parser.add_argument(
        "--auto",
        action="store_true",
        help="No Enter between beats (for a timed run-through).",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Hit Apify instead of the offline fixture.",
    )
    parser.add_argument(
        "--judge",
        default="auto",
        choices=("auto", "gemini", "anthropic", "openai", "heuristic"),
    )
    parser.add_argument(
        "--print-prompt",
        action="store_true",
        help="Print the Codex paste prompt and exit.",
    )
    return parser.parse_args()


CODEX_PROMPT = f"""$geo-citation-engineer

Query: {QUERY}
Brand: {BRAND}
Competitor: {COMPETITOR}
Draft: fixtures/draft.md

This is a 2.5 minute demo. Do not open Python source.
1. Run python demo.py --auto  (or the fetcher + eval scripts).
2. Show the citation GAP, then the rewritten page, then pass=true.
3. If Apify is slow, use --offline. Prefer --judge gemini when GEMINI_API_KEY is set.
"""


def main() -> int:
    load_dotenv()
    args = parse_args()
    if args.print_prompt:
        sys.stdout.write(CODEX_PROMPT)
        return 0

    judge = select_judge_provider(args.judge)
    print_banner()
    wait(args.auto)
    beat_draft(args.auto)
    beat_fetch(args.auto, live=args.live)
    beat_rewrite(args.auto)
    result = beat_eval(args.auto, judge=judge)
    beat_close(bool(result.get("pass")))
    return 0 if result.get("pass") else 2


if __name__ == "__main__":
    raise SystemExit(main())
