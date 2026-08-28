# GEO Citation Engineer

Reusable [Agent Skill](https://agentskills.io/specification) for Generative Engine Optimization (GEO). A coding agent fetches live Google AI Overview citations via [Apify](https://apify.com), finds when a competitor is cited and your brand is not, rewrites first-party copy with atomic facts, then proves the rewrite with evals.

Built for the Formidable Builders GTM Skillathon (Codex + Apify). MIT licensed.

## What it does

1. Pull Google AI Overview + SERP context (`apify/google-search-scraper`).
2. Detect citation gaps with local brand/competitor matching (no Link-prospecting add-on).
3. Optionally pull high-NPS G2 quotes (`automation-lab/g2-scraper`).
4. Rewrite the draft using GEO rules (short sentences, sourced stats, lists, quotes).
5. Score the result: deterministic GEO compliance + RAG-triad judge.

## Layout

```
.agents/skills/geo-citation-engineer/   Codex-discoverable skill
  SKILL.md
  agents/openai.yaml
  scripts/                              execute these; do not load them into context
  references/geo_rules.md
  assets/geo_report_template.md
fixtures/                               offline SERP, G2, draft, rewrite
```

## Setup

Python 3.11+.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# set APIFY_TOKEN for live fetches
```

Codex loads skills from `.agents/skills` in this repo automatically.

To install elsewhere:

```bash
# Codex (user scope)
cp -R .agents/skills/geo-citation-engineer "$HOME/.agents/skills/geo-citation-engineer"

# Claude Code
cp -R .agents/skills/geo-citation-engineer ".claude/skills/geo-citation-engineer"
```

## Run (offline demo — no Apify credits)

From the repository root:

```bash
python .agents/skills/geo-citation-engineer/scripts/apify_fetcher.py \
  --offline \
  --query "best crm for startups" \
  --brand "Acme" \
  --competitor "HubSpot" \
  --out output/serp.json

python .agents/skills/geo-citation-engineer/scripts/geo_compliance.py \
  --rewrite fixtures/rewrite.md \
  --source output/serp.json

python .agents/skills/geo-citation-engineer/scripts/eval_judge.py \
  --offline \
  --query "best crm for startups" \
  --rewrite fixtures/rewrite.md \
  --source output/serp.json \
  --original-draft fixtures/draft.md
```

`eval_judge.py` picks a judge in this order: Anthropic (`ANTHROPIC_API_KEY`), Gemini (`GEMINI_API_KEY` or `GOOGLE_API_KEY`), OpenAI (`OPENAI_API_KEY`), else heuristic. Force Gemini with `--judge gemini`. `--offline` skips paid APIs.

Gemini key: create one at [Google AI Studio](https://aistudio.google.com/api-keys), then:

```bash
echo 'GEMINI_API_KEY=your-key' >> .env
python .agents/skills/geo-citation-engineer/scripts/eval_judge.py \
  --judge gemini \
  --query "best crm for startups" \
  --rewrite fixtures/rewrite.md \
  --source output/serp.json \
  --original-draft fixtures/draft.md
```

## Live fetch

```bash
python .agents/skills/geo-citation-engineer/scripts/apify_fetcher.py \
  --query "best crm for startups" \
  --brand "Acme" \
  --competitor "HubSpot" \
  --g2-url "https://www.g2.com/products/acme/reviews" \
  --out output/serp.json
```

Default Actors: `apify/google-search-scraper` with `aiOverview.scrapeFullAiOverview`, `maxPagesPerQuery=1`. If no overview text is returned, the fetcher falls back to `apify/google-ai-overviews-scraper`. G2 failures are non-fatal.

ChatGPT / Perplexity / Gemini add-ons and Link prospecting stay off (pay-per-event). Fan-out is `peopleAlsoAsk` + `relatedQueries`. Brand mention flags are computed locally.

`fixtures/serp_raw.json` follows the official `apify/google-search-scraper` item shape (AI Overview, organic, PAA). Re-record a live fixture anytime with a token:

```bash
python .agents/skills/geo-citation-engineer/scripts/apify_fetcher.py \
  --query "best crm for startups" --brand "Acme" --competitor "HubSpot" \
  --out fixtures/serp_live.json
```

## Invoke the skill

In Codex: `$geo-citation-engineer` and provide query, brand, and a draft. The skill body is the workflow; the scripts are the sensors and evals.

## Tests

```bash
python -m pytest -q
```

## License

MIT. See [LICENSE](LICENSE).
