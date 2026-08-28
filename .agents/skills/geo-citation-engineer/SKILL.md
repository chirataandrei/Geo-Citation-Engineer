---
name: geo-citation-engineer
description: Automates Generative Engine Optimization (GEO). Fetches live AI-search citations via Apify, finds citation gaps vs competitors, and rewrites first-party content with atomic facts, statistics, lists, and customer quotes. Use when the user wants GEO analysis, AI Overview / ChatGPT / Perplexity visibility, citation gap analysis, or to rewrite a page so LLMs cite it.
license: MIT
compatibility: Python 3.11+. DuckDuckGo HTML fetch and offline eval are stdlib-only. Live Apify and LLM judges need `pip install -r requirements.txt` plus APIFY_TOKEN / GEMINI_API_KEY.
---

# GEO Citation Engineer

Turn a GTM keyword + brand draft into a citation-gap report and a GEO-rewritten page. Follow this workflow exactly. Do not invent statistics, quotes, or sources.

From this repository root, the 2.5-minute demo is one prompt: paste `demo/seed-prompt.md` and run `python3 demo.py --auto --judge heuristic`. That path uses DuckDuckGo HTML (stdlib) or the fixture. Do not pip install. Do not open script source.

This folder is the whole skill. Copy it onto another machine only if you are installing outside this repo.

## Install (clean environment)

Python 3.11+ on PATH. Then copy this directory:

```bash
mkdir -p "$HOME/.agents/skills"
cp -R geo-citation-engineer "$HOME/.agents/skills/geo-citation-engineer"
cd "$HOME/.agents/skills/geo-citation-engineer"
```

Claude Code:

```bash
cp -R geo-citation-engineer ".claude/skills/geo-citation-engineer"
cd .claude/skills/geo-citation-engineer
```

Offline demo (no pip, no tokens):

```bash
python3 scripts/apify_fetcher.py --offline \
  --query "best crm for startups" --brand Acme --competitor HubSpot --out serp.json
python3 scripts/geo_rewrite.py \
  --source serp.json --draft fixtures/draft.md --brand Acme --competitor HubSpot --out geo-report.md
python3 scripts/geo_compliance.py --rewrite geo-report.md --source serp.json
python3 scripts/eval_judge.py --offline --judge heuristic \
  --query "best crm for startups" --rewrite geo-report.md \
  --source serp.json --original-draft fixtures/draft.md
```

Live fetch / LLM judge — once per machine:

```bash
python3 -m pip install -r requirements.txt
cp .env.example .env
# set APIFY_TOKEN and optional GEMINI_API_KEY
```

`.env` is read from the working directory, this skill folder, or a parent folder.

For the 2.5-minute stage demo from the Skillathon repo root, paste `demo/seed-prompt.md` into Codex. That prompt runs `python3 demo.py --auto --judge heuristic`. Do not open script source.

## Checklist

Copy and tick as you go:

```
- [ ] Skill directory is the cwd (or script paths below are used as written)
- [ ] Inputs collected (query, brand, draft, optional competitor/G2 URL)
- [ ] apify_fetcher.py executed (do not read the script)
- [ ] references/geo_rules.md read
- [ ] Report written from the template
- [ ] geo_compliance.py executed
- [ ] eval_judge.py executed
- [ ] If groundedness failed: strip unsourced claims and retry evals once
```

## Step 1 — Collect inputs

Required:

- Search **query** (the industry question to win in AI Overviews)
- **Brand** name (and optional brand domain)
- Path to the user's **draft** page or paste the draft

Optional:

- **Competitor** name
- **G2 product URL** (example: `https://www.g2.com/products/hubspot/reviews`)
- Country / language codes (`us` / `en` defaults)

If anything required is missing, ask once, then stop.

## Step 2 — Fetch live signals

Execute the fetcher from **this skill directory**. Do **not** open or rewrite `scripts/apify_fetcher.py`. Stdout is the only source of truth.

```bash
python3 scripts/apify_fetcher.py \
  --query "QUERY" \
  --brand "BRAND" \
  --competitor "COMPETITOR" \
  --g2-url "G2_URL"
```

Flags:

- Default (no extra flag) — DuckDuckGo HTML, stdlib, no token. Falls back to the bundled fixture on timeout or empty results.
- `--offline` — use bundled `fixtures/serp_sample.json` (and G2 fixture).
- `--live` — Apify Google search / AI Overview. Needs `APIFY_TOKEN` and `pip install -r requirements.txt`.
- `--out PATH` — write JSON to disk as well as stdout.

Save the JSON. If the process exits non-zero, show stderr and stop.

## Step 3 — Load GEO rules

Only after JSON is in hand, read [references/geo_rules.md](references/geo_rules.md). Apply those constraints; do not add extra style essays.

## Step 4 — Write the GTM artifact

Copy [assets/geo_report_template.md](assets/geo_report_template.md) to a working file (for example `geo-report.md`). Fill every section.

Or generate a grounded draft from the JSON (stdlib, no invented stats):

```bash
python3 scripts/geo_rewrite.py \
  --source serp.json --draft path/to/draft.md \
  --brand "BRAND" --competitor "COMPETITOR" --out geo-report.md
```

Hard constraints:

- Every statistic, quote, and competitor claim must map to a field in the fetcher JSON (`ai_overview_text`, `cited_sources`, `organic`, `quotes`, `fan_out`).
- If the JSON has no number, do not invent one. Write a qualitative atomic fact instead.
- If `quotes` is empty, omit the quote block; do not fabricate reviews.
- Cover `fan_out` items as H2s, not only the head query.
- Change log must name the JSON field that justified each injection.

## Step 5 — Evaluate

Deterministic (always):

```bash
python3 scripts/geo_compliance.py \
  --rewrite geo-report.md \
  --source serp.json
```

LLM-as-a-judge (Anthropic, else Gemini via `GEMINI_API_KEY`, else OpenAI, else heuristic). Force Gemini with `--judge gemini`.

```bash
python3 scripts/eval_judge.py \
  --rewrite geo-report.md \
  --source serp.json \
  --query "QUERY" \
  --original-draft path/to/draft.md
```

Use `--offline` on the judge to skip paid LLM calls.

If `groundedness` fails or `geo_compliance.pass` is false:

1. Remove unsourced claims and sentences over 15 words.
2. Rewrite once.
3. Re-run both evals.
4. Stop after one retry and report remaining failures.

## Demo notes

Default fetch is DuckDuckGo HTML (no pip). Apify needs `APIFY_TOKEN` and `pip install -r requirements.txt` (`--live`). If the network is slow, rerun with `--offline` so the rest of the demo still shows gap JSON, rewrite, and evals.
