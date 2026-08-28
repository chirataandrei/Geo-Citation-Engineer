---
name: geo-citation-engineer
description: Finds out whether a named competitor is cited by AI search for a revenue keyword while your brand is not, then rewrites one page section so your brand becomes citable. Use for citation gap analysis, Google AI Overview visibility, GEO rewrites, or "why does AI recommend our competitor and not us".
license: MIT
compatibility: Python 3.11+. No credentials and no network needed; runs from a committed evidence snapshot. APIFY_TOKEN only enables optional live capture.
---

# GEO Citation Engineer

## The one job

**User:** a content marketer at a B2B or B2C software company.

**Problem:** for a keyword that drives revenue, Google's AI Overview cites a named competitor and never the user's brand.

**Job:** produce one citation-gap report plus one rewritten page section, with every fact traced to a captured evidence field.

**Boundary:** this skill drafts copy and stops. It does not publish, touch a CMS, run keyword research, cover ChatGPT or Perplexity, or claim the rewrite will earn a citation. If asked for any of those, say it is out of scope.

## Inputs

One brief JSON path. Nothing else. The brief names the query, brand, competitor, evidence snapshot, draft, and first-party `brand_facts`.

If the user gives a query and brand but no brief, copy `demo/input/stock-estate.brief.json`, edit the fields, and use that. If they give nothing, ask once for a brief path, then stop.

## Step 1 — Plan (one command)

```bash
python .agents/skills/geo-citation-engineer/scripts/run_geo.py plan --brief demo/input/stock-estate.brief.json
```

Do not open the script. Stdout is the only source of truth. It writes a report scaffold to `output/` and prints:

- `action` — `rewrite`, `decline`, or `abort`
- `gap_verdict`, plus `competitor_named_in_ai_overview` and `brand_named_in_ai_overview` — the load-bearing facts
- `opportunity` — `competitor_gap` (displace an incumbent answer) or `uncontested_answer` (nobody owns it yet)
- `evidence_level`, `sources_naming_competitor` of `sources_total`
- `fan_out_priority` — the three questions to answer
- `allowed_numbers.brand` — digits you may assert about the brand
- `allowed_numbers.evidence` — third-party digits, quotable only with the source named in the same sentence
- `allowed_claims` — the only first-party claims you may make
- `constraints` — the writing rules, already inlined so you do not need another file read

**Obey `action` before writing anything:**

| `action` | What you do |
|----------|-------------|
| `rewrite` | Continue to Step 2. Let `opportunity` set the angle: displace the incumbent, or claim an unowned answer. |
| `decline` | The brand is already cited. Report that, show the gap table, and stop. Do not rewrite. |
| `abort` | Evidence is too thin to claim a gap. Report that and stop. Do not rewrite, do not go looking for more evidence. |

## Step 2 — Write the rewrite (one edit)

Open the report at `report_path`. Replace the `AGENT-REWRITE` marker with the rewritten page. Fill the change log table underneath, naming the evidence field behind each injection.

Non-negotiable, and each one is machine-checked in Step 3:

- One fact per sentence, 15 words or fewer. Over 18 words is a hard fail.
- At least one bullet list inside `## Rewritten page`.
- An `###` heading for each question in `fan_out_priority`. Keep them inside `## Rewritten page`; a new `##` ends the scored section.
- Every digit must appear in `allowed_numbers.all`. Anything else scores as invented and fails.
- Numbers from `allowed_numbers.evidence` require the source named in the same sentence. Never restate a competitor's rating or download count as the brand's.
- Invent nothing. No statistic, quote, award, or customer count outside `allowed_claims`.
- If `allowed_numbers.brand` is empty, write qualitative atomic facts and attribute every digit you use.

## Step 3 — Score (one command)

```bash
python .agents/skills/geo-citation-engineer/scripts/run_geo.py score --brief demo/input/stock-estate.brief.json
```

Runs deterministic GEO compliance and an offline heuristic RAG-triad judge. No keys, no network.

Completion criteria — report is done when all of:

- `geo_compliance.pass` is `true`
- `judge.pass` is `true`
- `judge.invented_numbers` is empty
- the change log names an evidence field for every injection

**On failure:** the output names the failing checks. Fix exactly those, once, and re-run Step 3. If it still fails, stop and report the remaining failures honestly. Never loosen a check, never edit the scripts, never delete a failing sentence's evidence to make the check pass.

Exit codes: `0` pass, `2` scored but failed, `1` could not run (missing file, or the marker was never replaced).

## Optional — live capture

Only if the user asks and `APIFY_TOKEN` is set. **Measured at 1m36s** for one query against `apify/google-search-scraper` — that alone exceeds the 75s demo budget, so never do this on a demo clock. The committed snapshots exist precisely so the demo never needs it.

```bash
python .agents/skills/geo-citation-engineer/scripts/apify_fetcher.py \
  --query "QUERY" --brand "BRAND" --competitor "COMPETITOR" --out output/serp.json
```

Then point a brief's `snapshot` at that file. Without a token the fetcher exits non-zero and tells you to use a snapshot; that is expected, not an error to work around.

The fetcher normalises what the Actor returns: it trims Google interface chrome from the overview text, resolves `/goto?url=` citation stubs to publisher URLs (keeping `url_raw`), and collapses duplicate related queries. Never hand-edit a snapshot to make a gap look bigger.

## Reference

Read [references/geo_rules.md](references/geo_rules.md) only if the user asks *why* a rule exists. The rules themselves are already printed by Step 1.
