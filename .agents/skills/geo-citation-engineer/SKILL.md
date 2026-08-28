---
name: geo-citation-engineer
description: Automates Generative Engine Optimization (GEO). Fetches live AI-search citations via Apify, finds citation gaps vs competitors, and rewrites first-party content with atomic facts, statistics, lists, and customer quotes. Use when the user wants GEO analysis, AI Overview / ChatGPT / Perplexity visibility, citation gap analysis, or to rewrite a page so LLMs cite it.
license: MIT
compatibility: Requires Python 3.11+ and a valid APIFY_TOKEN for live fetches. Offline fixtures work without Apify.
---

# GEO Citation Engineer

Turn a GTM keyword + brand draft into a citation-gap report and a GEO-rewritten page. Follow this workflow exactly. Do not invent statistics, quotes, or sources.

## Checklist

Copy and tick as you go:

```
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

Execute the fetcher. Do **not** open or rewrite `scripts/apify_fetcher.py`. Stdout is the only source of truth.

From the repository root:

```bash
python .agents/skills/geo-citation-engineer/scripts/apify_fetcher.py \
  --query "QUERY" \
  --brand "BRAND" \
  --competitor "COMPETITOR" \
  --g2-url "G2_URL"
```

From this skill directory:

```bash
python scripts/apify_fetcher.py --query "QUERY" --brand "BRAND"
```

Flags:

- `--offline` — use `fixtures/serp_sample.json` (and optional G2 fixture). Use this if `APIFY_TOKEN` is missing or a live run times out.
- `--out PATH` — write JSON to disk as well as stdout.

Save the JSON. If the process exits non-zero, show stderr and stop.

## Step 3 — Load GEO rules

Only after JSON is in hand, read [references/geo_rules.md](references/geo_rules.md). Apply those constraints; do not add extra style essays.

## Step 4 — Write the GTM artifact

Copy [assets/geo_report_template.md](assets/geo_report_template.md) to a working file (for example `output/geo-report.md`). Fill every section.

Hard constraints:

- Every statistic, quote, and competitor claim must map to a field in the fetcher JSON (`ai_overview_text`, `cited_sources`, `organic`, `quotes`, `fan_out`).
- If the JSON has no number, do not invent one. Write a qualitative atomic fact instead.
- If `quotes` is empty, omit the quote block; do not fabricate reviews.
- Cover `fan_out` items as H2s, not only the head query.
- Change log must name the JSON field that justified each injection.

## Step 5 — Evaluate

Deterministic (always):

```bash
python .agents/skills/geo-citation-engineer/scripts/geo_compliance.py \
  --rewrite output/geo-report.md \
  --source output/serp.json
```

LLM-as-a-judge (Anthropic, else Gemini via `GEMINI_API_KEY`, else OpenAI, else heuristic). Force Gemini with `--judge gemini`.

```bash
python .agents/skills/geo-citation-engineer/scripts/eval_judge.py \
  --rewrite output/geo-report.md \
  --source output/serp.json \
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

Live path needs `APIFY_TOKEN`. If the Actor is slow, rerun the fetcher with `--offline` so the rest of the demo still shows gap JSON, rewrite, and evals.
