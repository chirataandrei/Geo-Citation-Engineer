# GEO Citation Engineer

A reusable [Agent Skill](https://agentskills.io/specification) that answers one question: **does Google's AI Overview recommend a named competitor for a keyword that matters to you, while never mentioning your brand?** If so, it rewrites one page section so your brand becomes citable — every fact traced to a captured evidence field, machine-checked so nothing is invented.

Built for the Formidable Builders GTM Skillathon, track **Dominate AI search**. MIT licensed.

**Runs with no credentials and no network.** Python 3.11+ and the standard library are enough.

## The one job

| | |
|---|---|
| **User** | A content marketer at a company with a revenue keyword they are losing. |
| **Problem** | Google's AI Overview names a competitor and never their brand. |
| **Job** | One citation-gap report plus one rewritten page section, every fact traced to evidence. |
| **Boundary** | Drafts copy and stops. No publishing, no CMS, no keyword research, no ChatGPT/Perplexity, no claim the rewrite will earn a citation. |

## Try it in 2 commands

```bash
python .agents/skills/geo-citation-engineer/scripts/run_geo.py plan --brief demo/input/stock-estate.brief.json
```

```bash
python .agents/skills/geo-citation-engineer/scripts/run_geo.py score --brief demo/input/stock-estate.brief.json --out-dir demo/output
```

0.32s combined from a fresh clone. See [DEMO.md](DEMO.md) for the run sheet and the stage fallback.

## The worked example

Live capture via `apify/google-search-scraper`, 2026-08-28 15:49 UTC, `us`/`en`. Google's AI Overview for **`best real estate crowdfunding platform europe`** opens:

> The top-rated real estate crowdfunding platforms in Europe include Estateguru for property-backed debt loans, InRento for rental income, and aggregator tools like BrikkApp…

It goes on to detail InRento, Reinvest24 and Raizers with returns, minimums and markets. **Stock.estate — a regulated European platform doing exactly this, ASF-authorised with EU passporting — is never mentioned.**

You cannot be recommended by an answer you are not in. That is the gap, and it is measured, not asserted: the verbatim overview, its citation URLs, the actor input and the retrieval timestamp are all in [the snapshot](demo/input/snapshots/best-real-estate-crowdfunding-platform-europe.2026-08-28.json), and the finished report is at [`demo/output/geo-report.stock-estate.md`](demo/output/geo-report.stock-estate.md).

## What makes the rewrite trustworthy

**The fact budget is split by who may claim what.** Stock.estate's own published figures (`from 100 EUR`, `19.9% all-in`) are assertable about the brand. Third-party numbers from the overview (`6% to 11%` — that is InRento's) are quotable *only* with the source named in the same sentence. Collapsing those two lists is exactly how a rewrite ends up claiming a competitor's numbers as its own, so the skill refuses to.

**It refuses more often than it writes.** Four outcomes, decided from the evidence before a word is drafted:

| Outcome | When | Behaviour |
|---------|------|-----------|
| `rewrite` + `competitor_gap` | Competitor named, brand absent | Draft copy that displaces the incumbent answer |
| `rewrite` + `uncontested_answer` | Neither named | Say the answer is unclaimed — do **not** invent a competitor |
| `decline` | Brand already named | No gap to close — stop |
| `abort` | Too little evidence to claim a gap | Refuse to assert one — stop |

Feed it the *same snapshot* with brand and competitor swapped and it flips from `rewrite` to `decline`. The verdict comes from the evidence, not the request.

**Two independent evals, no keys.** Deterministic GEO compliance (sentence length, list structure, sourced statistics, zero invented digits) plus an offline heuristic RAG-triad judge. Both must pass. Results, and the eleven defects the evals actually caught, are in [demo/evals.md](demo/evals.md).

**Honest provenance.** Each snapshot records the actor, its input, the request URL, the retrieval timestamp, and a `post_processing` list naming exactly what was changed: Google interface chrome trimmed at the footer, `/goto?url=` citation stubs resolved to publisher URLs with `url_raw` preserved, duplicate related queries collapsed. No wording was altered.

## Layout

```
.agents/skills/geo-citation-engineer/   entry skill
  SKILL.md                             the workflow — 2 commands, 1 edit
  agents/openai.yaml
  scripts/
    run_geo.py                         plan + score orchestrator (demo path)
    apify_fetcher.py                   optional live capture
    geo_compliance.py                  deterministic eval
    eval_judge.py                      RAG-triad judge (LLM or heuristic)
    geo_lib.py
  references/geo_rules.md
  assets/geo_report_template.md
demo/
  seed-prompt.md                       what to paste into Codex
  input/                               briefs + live evidence snapshots
  output/                              committed finished reports (stage fallback)
  evals.md                             3 cases + reusability + defects + limits
fixtures/                              synthetic unit-test data only — never evidence
tests/test_geo.py                      22 tests
DEMO.md                                run sheet
submission.json                        manifest
```

`plan` writes to the gitignored `output/` so a live run never overwrites the committed fallback in `demo/output/`.

## Reusability

A new case is a new brief. No code edits.

| Brief | Query | Result |
|-------|-------|--------|
| [`attio.brief.json`](demo/input/attio.brief.json) | `best crm for startups` | Google answers *"The HubSpot CRM is the best overall choice for startups"*. Attio absent. No first-party facts supplied, so the rewrite degrades to qualitative claims with every digit attributed. |
| [`formidable-builders.brief.json`](demo/input/formidable-builders.brief.json) | `open source agent skills for coding agents` | Nobody is named. Reported as an `uncontested_answer` rather than a fabricated competitor gap. |

To add your own: copy a brief, set `query`, `brand`, `competitor`, `snapshot`, `draft`, and `brand_facts.claims`.

## Optional live capture

**Measured at 1m36s for one query**, which alone exceeds the 75s demo gate. That is why it is off the demo path and the snapshots are committed.

```bash
cp .env.example .env    # set APIFY_TOKEN
pip install -r requirements.txt
python .agents/skills/geo-citation-engineer/scripts/apify_fetcher.py \
  --query "best real estate crowdfunding platform europe" \
  --brand "Stock.estate" --competitor "EstateGuru" --out output/serp.json
```

Then point a brief's `snapshot` at `output/serp.json`. Default actor is `apify/google-search-scraper` with `aiOverview.scrapeFullAiOverview`, falling back to `apify/google-ai-overviews-scraper`. Works with `apify-client` 2.x and 3.x. Without a token the fetcher exits non-zero and says to use a snapshot — that is the graceful degradation, not a failure.

`eval_judge.py` uses Anthropic, then Gemini, then OpenAI if a key is present, else the heuristic. `--offline` skips paid APIs.

## Install elsewhere

```bash
# Codex (user scope)
cp -R .agents/skills/geo-citation-engineer "$HOME/.agents/skills/geo-citation-engineer"

# Claude Code
cp -R .agents/skills/geo-citation-engineer ".claude/skills/geo-citation-engineer"
```

## Limitations

Stated in full in [demo/evals.md](demo/evals.md). The main ones: all captures are point-in-time `us`/`en` on 2026-08-28, and AI Overviews are volatile, personalised, and not always rendered. Citation URLs are reconstructed from Google redirect stubs by matching against organic results. Brand matching is literal substring matching, so counts are floors. The offline judge is a heuristic and cannot catch a fluent claim that is qualitatively false. Stock.estate's figures are its own published claims, not verified performance, and nothing here is investment advice. Nothing measures whether a published rewrite later earned a citation.

## License

MIT. See [LICENSE](LICENSE).
