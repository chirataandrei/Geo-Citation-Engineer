#!/usr/bin/env python3
"""Stage demo: cinematic terminal + HTML board. One command."""

from __future__ import annotations

import argparse
import html
import json
import os
import shutil
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCRIPTS = ROOT / ".agents" / "skills" / "geo-citation-engineer" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from eval_judge import select_judge_provider  # noqa: E402
from geo_lib import load_dotenv, section_named  # noqa: E402

QUERY = "best crm for startups"
BRAND = "Acme"
COMPETITOR = "HubSpot"
TEAL = "#0F766E"
DRAFT_PATH = ROOT / "demo" / "input" / "draft.md"
REWRITE_PATH = ROOT / "demo" / "output" / "geo-report.md"
SHOW_PATH = ROOT / "demo" / "show.html"


def _tty() -> bool:
    return sys.stdout.isatty()


def _cols() -> int:
    try:
        return shutil.get_terminal_size().columns
    except OSError:
        return 80


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


def bright(text: str) -> str:
    return _c("1;36", text)


def wait(auto: bool) -> None:
    if auto:
        time.sleep(0.2)
        return
    try:
        input(dim("  [Enter]  "))
    except EOFError:
        pass


def excerpt(text: str, limit: int = 420) -> str:
    compact = "\n".join(line.rstrip() for line in text.strip().splitlines() if line.strip())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def highlight_geo(text: str) -> str:
    out = []
    for line in text.splitlines():
        low = line.lower()
        if "64%" in line or "lina k" in low or "replaced our spreadsheet" in low:
            out.append(bright(line))
        else:
            out.append(line)
    return "\n".join(out)


def type_line(text: str, auto: bool) -> None:
    if auto or not _tty():
        print(f"  {text}")
        return
    sys.stdout.write("  ")
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(0.008)
    sys.stdout.write("\n")
    sys.stdout.flush()


def run_script(name: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPTS / name), *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def run_script_spin(name: str, args: list[str], auto: bool, label: str) -> subprocess.CompletedProcess[str]:
    if auto or not _tty():
        return run_script(name, args)
    done = threading.Event()
    frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def spin() -> None:
        i = 0
        while not done.is_set():
            sys.stdout.write(f"\r  {cyan(frames[i % len(frames)])}  {label}   ")
            sys.stdout.flush()
            time.sleep(0.08)
            i += 1
        sys.stdout.write("\r" + " " * 48 + "\r")
        sys.stdout.flush()

    thread = threading.Thread(target=spin, daemon=True)
    thread.start()
    try:
        return run_script(name, args)
    finally:
        done.set()
        thread.join(timeout=0.4)


def print_banner() -> None:
    width = max(56, min(_cols() - 2, 72))
    inner = "GEO  ·  citation engineer"
    pad = max(0, width - 4 - len(inner))
    print()
    print(bold("┌" + "─" * (width - 2) + "┐"))
    print(bold("│  " + inner + " " * pad + "│"))
    print(bold("└" + "─" * (width - 2) + "┘"))
    print()
    print(f"  {dim('query')}   {QUERY}")
    print(f"  {dim('fight')}   {bold(BRAND)}  vs  {COMPETITOR}")
    print()
    print(dim("  Make first-party pages get cited in AI Overviews."))


def beat_draft(auto: bool) -> str:
    print()
    print(bold("  01  INVISIBLE"))
    print(dim("  ────────────────────────────────────────"))
    print()
    draft = DRAFT_PATH.read_text(encoding="utf-8")
    for line in excerpt(draft, 480).splitlines():
        print(red("  " + line))
    print()
    print(dim("  autopsy   0 stats  ·  0 quotes  ·  sentences too long to cite"))
    wait(auto)
    return draft


def beat_fetch(auto: bool, live: bool) -> dict:
    print()
    print(bold("  02  THE ENGINE ALREADY PICKED A WINNER"))
    print(dim("  ────────────────────────────────────────"))
    print()
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
    if not live:
        cmd.insert(0, "--offline")
        print(dim("  sensor   apify_fetcher.py  ·  fixture (same contract as live)"))
    else:
        print(dim("  sensor   apify_fetcher.py  ·  live Apify"))
    proc = run_script_spin("apify_fetcher.py", cmd, auto, "pulling signal…")
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout)
        if live:
            print(dim("  live failed — falling back offline"))
            return beat_fetch(auto, live=False)
        raise SystemExit(proc.returncode)
    payload = json.loads(out.read_text(encoding="utf-8"))
    overview = (payload.get("ai_overview_text") or "").strip()
    print()
    print(cyan("  AI Overview"))
    type_line(excerpt(overview, 240), auto)
    print()
    brand_hit = bool(payload.get("brand_mentioned_in_ai"))
    competitor_hit = bool(payload.get("competitor_mentioned_in_ai"))
    gap = str(payload.get("gap") or "?")
    acme = green("cited") if brand_hit else red("not cited")
    hub = green("cited") if competitor_hit else red("not cited")
    gap_col = red(gap) if "absent" in gap.lower() else green(gap)
    print()
    print(bold("  GAP"))
    print(f"  ACME        {acme}")
    print(f"  HUBSPOT     {hub}")
    print(f"  VERDICT     {gap_col}")
    fan = payload.get("fan_out") or []
    if fan:
        print()
        print(dim("  fan-out — queries the model actually retrieves"))
        for item in fan[:4]:
            print(f"    {cyan('›')} {item}")
    wait(auto)
    return payload


def beat_rewrite(auto: bool) -> str:
    print()
    print(bold("  03  THE PAGE BUILT TO GET STOLEN"))
    print(dim("  ────────────────────────────────────────"))
    print()
    rewrite = REWRITE_PATH.read_text(encoding="utf-8")
    body = section_named(rewrite, "Rewritten page") or rewrite
    draft = DRAFT_PATH.read_text(encoding="utf-8")
    width = _cols()
    if width >= 100:
        left_w = max(36, (width - 8) // 2)
        right_w = left_w
        left_lines = excerpt(draft, 360).splitlines()
        right_lines = excerpt(body, 520).splitlines()
        rows = max(len(left_lines), len(right_lines), 1)
        print(f"  {red('BEFORE'.ljust(left_w))}  {green('AFTER'.ljust(right_w))}")
        print(dim("  " + "─" * left_w + "  " + "─" * right_w))
        for i in range(min(rows, 12)):
            left = left_lines[i] if i < len(left_lines) else ""
            right = right_lines[i] if i < len(right_lines) else ""
            right_pad = right[:right_w].ljust(right_w)
            low = right.lower()
            if "64%" in right or "lina k" in low or "replaced our spreadsheet" in low:
                right_pad = bright(right_pad)
            print(f"  {dim(left[:left_w].ljust(left_w))}  {right_pad}")
    else:
        print(highlight_geo("\n".join("  " + line for line in excerpt(body, 720).splitlines())))
    print()
    print(green("  64% sourced  ·  list  ·  G2 quote  ·  fan-out H2s"))
    wait(auto)
    return body


def animate_bar(name: str, value: float, auto: bool) -> None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        num = 0.0
    filled_final = max(0, min(10, round(num * 10)))
    steps = 1 if auto or not _tty() else 10
    delay = 0.0 if steps == 1 else 0.01
    for step in range(1, steps + 1):
        filled = filled_final if steps == 1 else round(filled_final * step / steps)
        bar = ("█" * filled) + ("░" * (10 - filled))
        line = f"  {name:<20} {num:>4.2f}  {bar}"
        if steps == 1:
            print(line)
            return
        sys.stdout.write("\r" + line)
        sys.stdout.flush()
        time.sleep(delay)
    sys.stdout.write("\n")


def beat_eval(auto: bool, judge: str) -> dict:
    print()
    print(bold("  04  PROOF"))
    print(dim("  ────────────────────────────────────────"))
    print()
    print(dim(f"  judge    {judge}"))
    args = [
        "--query",
        QUERY,
        "--rewrite",
        str(REWRITE_PATH),
        "--source",
        str(ROOT / "output" / "serp.json"),
        "--original-draft",
        str(DRAFT_PATH),
        "--judge",
        judge,
    ]
    proc = run_script_spin("eval_judge.py", args, auto, "scoring rewrite…")
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
    print()
    animate_bar("context", scores.get("context_relevance"), auto)
    animate_bar("groundedness", scores.get("groundedness"), auto)
    animate_bar("answer", scores.get("answer_relevance"), auto)
    animate_bar("GEO compliance", compliance.get("geo_compliance_score"), auto)
    print()
    passed = bool(result.get("pass"))
    stamp = green("●  PASS") if passed else red("●  FAIL")
    print(f"  {bold('verdict')}   {stamp}    {dim('judge=' + str(result.get('judge')))}")
    wait(auto)
    return result


def beat_close(passed: bool, opened: bool) -> None:
    print()
    print(bold("  ────────────────────────────────────────"))
    print(f"  skill    {cyan('$geo-citation-engineer')}")
    print(dim("  MIT  ·  Codex / Claude Code  ·  evals travel with the skill"))
    if opened:
        print(f"  board    {SHOW_PATH}")
    print()
    if passed:
        print(green("  Ready."))
    else:
        print(red("  Eval failed — try --judge heuristic."))
    print()


def render_show_html(payload: dict, judged: dict, draft: str, rewrite_body: str) -> str:
    gap = html.escape(str(payload.get("gap") or ""))
    brand_hit = bool(payload.get("brand_mentioned_in_ai"))
    competitor_hit = bool(payload.get("competitor_mentioned_in_ai"))
    overview = html.escape(excerpt(str(payload.get("ai_overview_text") or ""), 360))
    draft_h = html.escape(excerpt(draft, 900)).replace("\n", "<br>\n")
    after_h = html.escape(excerpt(rewrite_body, 1200)).replace("\n", "<br>\n")
    scores = judged.get("scores") or {}
    compliance = judged.get("geo_compliance") or {}
    passed = bool(judged.get("pass"))
    pill_class = "bad" if "absent" in gap.lower() else "ok"
    acme_cls = "ok" if brand_hit else "bad"
    hub_cls = "ok" if competitor_hit else "bad"

    def pct(key: str, blob: dict) -> int:
        try:
            return int(round(float(blob.get(key) or 0) * 100))
        except (TypeError, ValueError):
            return 0

    meters = [
        ("Context", pct("context_relevance", scores)),
        ("Grounded", pct("groundedness", scores)),
        ("Answer", pct("answer_relevance", scores)),
        ("GEO", pct("geo_compliance_score", compliance)),
    ]
    meters_html = "".join(
        f'<div class="meter"><span>{html.escape(label)}</span>'
        f'<div class="track"><i style="width:{value}%"></i></div><b>{value}%</b></div>'
        for label, value in meters
    )
    fan = payload.get("fan_out") or []
    fan_html = "".join(f"<li>{html.escape(str(item))}</li>" for item in fan[:5])
    verdict = "PASS" if passed else "FAIL"
    verdict_cls = "ok" if passed else "bad"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>GEO Citation Engineer</title>
  <style>
    :root {{ --teal: {TEAL}; --bg: #07110e; --card: #0d1a16; --ink: #e7f3ee; --mute: #8aa399; }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0; background: var(--bg); color: var(--ink);
      font: 16px/1.45 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
    }}
    header {{
      padding: 28px 36px 18px; border-bottom: 1px solid #1c332c;
      display: flex; justify-content: space-between; align-items: flex-start; gap: 16px;
    }}
    header strong {{ color: var(--teal); letter-spacing: .12em; font-size: 12px; }}
    h1 {{ margin: 6px 0 0; font-size: 28px; font-weight: 650; }}
    .pill {{
      border-radius: 999px; padding: 8px 14px; font-size: 13px; font-weight: 650;
      white-space: nowrap; align-self: center;
    }}
    .pill.bad {{ background: #3b1515; color: #ffb4b4; }}
    .pill.ok {{ background: #12382f; color: #9ee7cf; }}
    .row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; padding: 22px 36px; }}
    @media (max-width: 860px) {{ .row {{ grid-template-columns: 1fr; }} }}
    .card {{ background: var(--card); border: 1px solid #1c332c; border-radius: 14px; padding: 18px 20px; }}
    .card h2 {{ margin: 0 0 12px; font-size: 12px; letter-spacing: .14em; color: var(--mute); }}
    .before {{ color: #c9a4a4; }}
    .after {{ color: #d7f5ea; }}
    .cite {{ display: flex; gap: 12px; padding: 0 36px 8px; }}
    .cite div {{ flex: 1; background: var(--card); border-radius: 12px; padding: 14px 16px; border: 1px solid #1c332c; }}
    .cite em {{ display: block; font-style: normal; color: var(--mute); font-size: 12px; letter-spacing: .12em; }}
    .ok-t {{ color: #7ee0c2; font-weight: 700; }}
    .bad-t {{ color: #ff8d8d; font-weight: 700; }}
    .overview {{ padding: 0 36px 12px; color: var(--mute); font-size: 15px; }}
    .scores {{ padding: 8px 36px 28px; display: grid; grid-template-columns: 1fr auto; gap: 20px; align-items: center; }}
    .meter {{ margin: 8px 0; display: grid; grid-template-columns: 88px 1fr 48px; gap: 10px; align-items: center; }}
    .meter .track {{ background: #1c332c; border-radius: 99px; height: 8px; overflow: hidden; }}
    .meter i {{ display: block; height: 8px; background: var(--teal); border-radius: 99px; }}
    .stamp {{
      font-size: 42px; font-weight: 800; letter-spacing: .08em;
      border-radius: 16px; padding: 18px 28px; text-align: center;
    }}
    .stamp.ok {{ background: #12382f; color: #9ee7cf; }}
    .stamp.bad {{ background: #3b1515; color: #ffb4b4; }}
    footer {{ padding: 0 36px 28px; color: var(--mute); font-size: 13px; }}
    ul {{ margin: 8px 0 0; padding-left: 18px; color: var(--mute); }}
  </style>
</head>
<body>
  <header>
    <div>
      <strong>GEO CITATION ENGINEER</strong>
      <h1>{html.escape(QUERY)}</h1>
    </div>
    <div class="pill {pill_class}">{gap}</div>
  </header>
  <p class="overview">{overview}</p>
  <div class="cite">
    <div><em>ACME</em><span class="{acme_cls}-t">{"cited" if brand_hit else "not cited"}</span></div>
    <div><em>HUBSPOT</em><span class="{hub_cls}-t">{"cited" if competitor_hit else "not cited"}</span></div>
  </div>
  <div class="row">
    <article class="card before"><h2>CURRENT PAGE</h2><div>{draft_h}</div></article>
    <article class="card after"><h2>GEO PAGE</h2><div>{after_h}</div></article>
  </div>
  <div class="scores">
    <div>{meters_html}</div>
    <div class="stamp {verdict_cls}">{verdict}</div>
  </div>
  <div class="card" style="margin:0 36px 20px"><h2>FAN-OUT</h2><ul>{fan_html}</ul></div>
  <footer>$geo-citation-engineer · MIT · evals travel with the skill</footer>
</body>
</html>
"""


def write_show(payload: dict, judged: dict, draft: str, rewrite_body: str, open_browser: bool) -> bool:
    SHOW_PATH.write_text(render_show_html(payload, judged, draft, rewrite_body), encoding="utf-8")
    if not open_browser:
        return False
    if os.environ.get("GEO_DEMO_NO_OPEN"):
        return False
    webbrowser.open(SHOW_PATH.resolve().as_uri())
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="GEO Citation Engineer cinematic demo.")
    parser.add_argument("--auto", action="store_true", help="No Enter between beats.")
    parser.add_argument("--live", action="store_true", help="Hit Apify instead of fixtures.")
    parser.add_argument(
        "--judge",
        default="auto",
        choices=("auto", "gemini", "anthropic", "openai", "heuristic"),
    )
    parser.add_argument("--web", dest="web", action="store_true", help="Write and open HTML board.")
    parser.add_argument("--no-web", dest="web", action="store_false", help="Skip HTML / browser.")
    parser.set_defaults(web=True)
    parser.add_argument("--print-prompt", action="store_true")
    return parser.parse_args()


CODEX_PROMPT = f"""$geo-citation-engineer

Query: {QUERY}
Brand: {BRAND}
Competitor: {COMPETITOR}
Draft: demo/input/draft.md

This is a 2.5 minute demo. Do not open Python source.
1. Run python demo.py
2. Show the GAP stamp, then the GEO page, then PASS.
3. Glance at demo/show.html on the second screen.
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
    draft = beat_draft(args.auto)
    payload = beat_fetch(args.auto, live=args.live)
    rewrite_body = beat_rewrite(args.auto)
    judged = beat_eval(args.auto, judge=judge)
    if args.web:
        write_show(payload, judged, draft, rewrite_body, open_browser=True)
    beat_close(bool(judged.get("pass")), args.web)
    return 0 if judged.get("pass") else 2


if __name__ == "__main__":
    raise SystemExit(main())
