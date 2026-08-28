# GEO Citation Engineer

A reusable [Agent Skill](https://agentskills.io/specification) that answers one question: **is a named competitor cited by AI search for a keyword that matters to you, while your brand is not?** If yes, it rewrites one page section so your brand becomes citable — with every fact traced to a captured evidence field, and machine-checked so nothing is invented.

Built for the Formidable Builders GTM Skillathon, track **Dominate AI search**. MIT licensed.

**Runs with no credentials and no network.** Python 3.11+ and the standard library are enough.

## The one job

| | |
|---|---|
| **User** | A content marketer at a B2B or B2C software company. |
| **Problem** | For a revenue keyword, AI search cites a named competitor and never their brand. |
| **Job** | One citation-gap report plus one rewritten page section, every fact traced to evidence. |
| **Boundary** | Drafts copy and stops. No publishing, no CMS, no keyword research, no ChatGPT/Perplexity, no claim the rewrite will earn a citation. |

## Try it in 3 commands

```bash
python .agents/skills/geo-citation-engineer/scripts/run_geo.py plan --brief demo/input/bible-chat.brief.json
```

```bash
python .agents/skills/geo-citation-engineer/scripts/run_geo.py score --brief demo/input/bible-chat.brief.json --out-dir demo/output
```

```bash
python -m pip install pytest && python -m pytest -q
```

`plan` takes ~0.17s, `score` ~0.19s. See [DEMO.md](DEMO.md) for the full run sheet and the stage fallback.

## The worked example

Real capture for **`best bible study app`**, 2026-08-28, `us`/`en`:

- **3 of 8** sources Google surfaced name **YouVersion** — a listicle at rootedandgrounded.com, a 2026 comparison at faithgpt.io, and the top answer in an r/Bible thread.
- **0 of 8** name **Bible Chat**.

If you are not in the citable set, no AI answer can cite you. That is the gap, and it is measured, not asserted — [`demo/input/snapshots/best-bible-study-app.2026-08-28.json`](demo/input/snapshots/best-bible-study-app.2026-08-28.json) carries the request URL and retrieval timestamp, and the finished report is at [`demo/output/geo-report.bible-chat.md`](demo/output/geo-report.bible-chat.md).

## What makes the rewrite trustworthy

**The fact budget is split by who may claim what.** First-party numbers from `brand_facts` are assertable about the brand. Third-party numbers from the SERP are quotable only with the source named in the same sentence. Collapsing those two lists is how a rewrite ends up claiming a competitor's star rating as its own — so the skill refuses to.

**It refuses more often than it writes.** Three outcomes, decided from the evidence before a word is drafted:

| `action` | When | Behaviour |
|----------|------|-----------|
| `rewrite` | Competitor cited, brand absent, enough evidence | Draft the rewrite |
| `decline` | Brand already in the citable set | No gap to close — stop |
| `abort` | Too few sources to claim a gap | Refuse to assert one — stop |

Feed it the *same* snapshot with brand and competitor swapped and it flips from `rewrite` to `decline`. The verdict comes from the evidence, not the request.

**Two independent evals, no keys.** Deterministic GEO compliance (sentence length, list structure, sourced statistics, zero invented digits) plus an offline heuristic RAG-triad judge. Both must pass. Results and the defects they caught are in [demo/evals.md](demo/evals.md).

## Layout

```
.agents/skills/geo-citation-engineer/   entry skill
  SKILL.md                             the workflow — 2 commands, 1 edit
  agents/openai.yaml
  scripts/
    run_geo.py                         plan + score orchestrator (demo path)
    apify_fetcher.py                   optional live capture
    geo_compliance.py                  deterministic eval
    eval_judge.py                       RAG-triad judge (LLM or heuristic)
    geo_lib.py
  references/geo_rules.md
  assets/geo_report_template.md
demo/
  seed-prompt.md                       what to paste into Codex
  input/                               briefs + real evidence snapshots
  output/                              committed finished reports (stage fallback)
  evals.md                             3 cases + reusability + known limits
fixtures/                              synthetic unit-test data only — never evidence
tests/test_geo.py                      18 tests
DEMO.md                                run sheet
submission.json                        manifest
```

`plan` writes to the gitignored `output/` so a live run never overwrites the committed fallback in `demo/output/`.

## Reusability

A new case is a new brief. No code edits. [`demo/input/attio.brief.json`](demo/input/attio.brief.json) points the same skill at `best crm for startups` in an unrelated industry; because no first-party facts were collected for that brand, the rewrite degrades to qualitative claims with every digit attributed. Both evals still pass.

To add your own: copy a brief, set `query`, `brand`, `competitor`, `snapshot`, `draft`, and `brand_facts.claims`.

## Optional live capture

Costs Apify credits and takes 30–90s, so it is off the demo path.

```bash
cp .env.example .env   # set APIFY_TOKEN
pip install -r requirements.txt
python .agents/skills/geo-citation-engineer/scripts/apify_fetcher.py \
  --query "best bible study app" --brand "Bible Chat" --competitor "YouVersion" \
  --out output/serp.json
```

Then point a brief's `snapshot` at `output/serp.json`. Default Actor is `apify/google-search-scraper` with `aiOverview.scrapeFullAiOverview`, falling back to `apify/google-ai-overviews-scraper`. ChatGPT/Perplexity add-ons and link prospecting stay off (pay-per-event).

`eval_judge.py` will use Anthropic, then Gemini, then OpenAI if a key is present, else the heuristic. `--offline` skips paid APIs.

## Install elsewhere

```bash
# Codex (user scope)
cp -R .agents/skills/geo-citation-engineer "$HOME/.agents/skills/geo-citation-engineer"

# Claude Code
cp -R .agents/skills/geo-citation-engineer ".claude/skills/geo-citation-engineer"
```

## Limitations

Stated in full in [demo/evals.md](demo/evals.md). The main ones: neither real snapshot contains AI Overview text, because Google does not render overviews to automated browsers and the demo path has no Apify credentials — the gap is measured against the organic citable set instead. Brand matching is literal substring matching, so `3 of 8` is a floor. Captures are point-in-time and AI answers are volatile. Nothing here measures whether a published rewrite later earned a citation.

## License

MIT. See [LICENSE](LICENSE).
