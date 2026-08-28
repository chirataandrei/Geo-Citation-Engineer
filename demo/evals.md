# Evals

Every result below was produced by running the commands shown, on HEAD of this branch, Python 3.13.9, Windows 11, with **no credentials and no network**. The evidence snapshots were captured live from Google via Apify earlier the same day; the evals themselves never call out.

```bash
python .agents/skills/geo-citation-engineer/scripts/run_geo.py plan  --brief demo/input/<case>.brief.json
python .agents/skills/geo-citation-engineer/scripts/run_geo.py score --brief demo/input/<case>.brief.json --out-dir demo/output
python -m pip install pytest && python -m pytest -q      # 22 tests, optional
```

## The three cases

| # | Case | Input | What correct behaviour is | Observed result | Pass/Fail |
|---|------|-------|---------------------------|-----------------|-----------|
| 1 | **Intended use** — competitor owns the answer, rewrite warranted | `demo/input/stock-estate.brief.json` — live Google AI Overview for `best real estate crowdfunding platform europe`, brand Stock.estate, competitor EstateGuru | Detect that the AI Overview names the competitor and never the brand. Produce a rewrite. Both evals green, zero invented numbers. | `action: rewrite`, `opportunity: competitor_gap`, `gap_verdict: "competitor cited; brand absent"`. `competitor_named_in_ai_overview: true`, `brand_named_in_ai_overview: false`. Compliance `1.0`, `pass: true`. Judge `context 1.0 / groundedness 1.0 / answer 1.0`, `pass: true`, `invented_numbers: []`. | **Pass** |
| 2 | **Insufficient evidence** — must refuse to claim a gap | `demo/input/thin-evidence.brief.json` — labelled synthetic fixture: one thin source, no AI Overview, no numeric facts | Refuse. Do not assert a citation gap. Do not rewrite. Do not go hunting for more evidence. | `evidence_level: insufficient`, `action: abort`, reason `"Only 1 cited source(s) and no AI Overview text."` Report written with an explicit no-rewrite outcome, `scored: false`. No rewrite produced. | **Pass** |
| 3 | **Failure / exclusion** — brand already cited, a rewrite would be wasted work | `demo/input/estateguru-already-cited.brief.json` — the *same live snapshot as case 1* with brand and competitor swapped | Recognise the brand is already in the answer and decline. There is no gap to close. | `gap_verdict: "brand cited; competitor absent"`, `action: decline`, reason `"Brand is already inside the citable set … no rewrite is warranted."` No rewrite produced. | **Pass** |

Case 3 shares its evidence file with case 1 deliberately. It proves the verdict is computed from the evidence rather than assumed from the request: the same Google AI Overview yields `rewrite` for Stock.estate and `decline` for EstateGuru.

## Reusability check

Different industry, different brand, different competitor, **zero code or skill edits** — only a new brief pointing at a new snapshot.

| Case | Input | Observed result | Pass/Fail |
|------|-------|-----------------|-----------|
| Cross-industry | `demo/input/attio.brief.json` — live AI Overview for `best crm for startups`, brand Attio, competitor HubSpot. Google's answer opens *"The HubSpot CRM is the best overall choice for startups"*. | `action: rewrite`, `opportunity: competitor_gap`. `allowed_numbers.brand` is empty because no first-party facts were collected, so the rewrite degraded to qualitative claims with every digit attributed to its publisher. Compliance `1.0`, judge `1.0 / 1.0 / 1.0`, `invented_numbers: []`. | **Pass** |
| Different opportunity shape | `demo/input/formidable-builders.brief.json` — live AI Overview for `open source agent skills for coding agents`, brand Formidable Builders | Neither brand nor competitor is named, so the skill switched framing: `opportunity: uncontested_answer` rather than inventing a competitor gap. Compliance `1.0`, judge `1.0 / 1.0 / 1.0`, `invented_numbers: []`. | **Pass** |

The second row matters more than it looks. A tool that only knows how to say "your competitor beat you" would have fabricated an incumbent here. This one reports that the answer is unclaimed and says plainly that it is a weaker signal.

## Defects these evals actually caught

An all-green table on the first run would mean the evals were not doing any work. These are real failures found and fixed while building, each reproducible by reverting the named change.

| Defect | How it surfaced | Fix |
|--------|-----------------|-----|
| Live capture silently returned nothing. `apify-client` 3.x renamed `timeout_secs`/`wait_secs` to `run_timeout`/`wait_duration` (as `timedelta`), so every Actor call raised `TypeError` and the fetcher fell through to an empty payload. | First live run | `_actor_call` now tries 3.x kwargs, then 2.x, then bare, and `_as_dict` handles both the 2.x dict and the 3.x typed `Run`. `requirements.txt` no longer pins `<3`. |
| `apify-client` 3.x defaults `logger='default'`, which streams Actor logs to **stdout** — the same stdout the skill contract says is JSON-only. | Reading the 3.x signature | Pass `logger=None` on the 3.x call path. |
| Google interface chrome was captured as part of the AI Overview: *"AI responses may include mistakes"*, *"This public link is valid for seven days"*, *"Save to Google Drive"*. Its digits entered the fact budget as quotable evidence. | Case 1 | `strip_overview_chrome()` trims at the first known footer marker. Two distinct footer variants were needed (`AI responses may include mistakes` and `AI can make mistakes`) before all three captures came back clean. |
| AI Overview citation URLs are opaque `/goto?url=CAES…` redirect stubs. An unresolvable URL is worthless as evidence, and "source URL" is the whole point. | Case 1 | `resolve_cited_urls()` matches each citation's publisher against the organic results, which carry real URLs. All 3 stubs in case 1 resolved; `url_raw` keeps the original; anything unmatched is flagged, not guessed. |
| The publisher heuristic assumed the publisher is the **last** title segment, so `"BrikkApp \| Invest in Real Estate"` produced the slug `investinrealestate` and failed to match `brikkapp.com`. | Case 1 | `_publisher_slugs()` tries every title segment, first and last, plus the leading word. |
| The two evals contradicted each other: compliance passed a rewrite at `1.0` while the judge returned `groundedness: 0.0` and flagged every first-party number as invented. | An earlier case | `eval_judge._blob()` did not include `brand_facts.claims`, so legitimate first-party facts looked unsourced. Added the claims and `organic` to the blob. |
| `40M` yielded no usable number, so a rewrite saying "40 million" would have been scored as inventing `40`. | An earlier case | `NUMBER_RE` required a trailing `\b`, which `40M` does not have. Dropped it so source and rewrite extract symmetrically. |
| A competitor's rating and review count sat in the same allow-list as the brand's own metrics, inviting a rewrite that claimed them for the brand. | An earlier case | Split the budget into `allowed_numbers.brand` (assertable) and `allowed_numbers.evidence` (quotable only with the source named in the sentence). |
| `plan` silently overwrote the committed fallback report — the artifact the demo depends on. | Second run of case 1 | `--out-dir` defaults to the gitignored `output/`; `demo/output/` is written only when explicitly targeted. |
| `demo/output/` was **absent from a fresh clone**, which fails the submission structure gate outright. | Cloning the repo to a temp dir and listing it | `.gitignore` had an unanchored `output/`, which matches at any depth. Changed to `/output/`. |
| `--offline` defaulted to the synthetic Acme fixture and auto-loaded a default G2 fixture, which would have spliced synthetic review quotes into a real capture. | Reading the offline branch | Default snapshot is now real captured evidence; a G2 fixture loads only when named explicitly. |
| Nine fan-out questions were handed over for H3 coverage, including near-duplicates and the genuinely captured but off-topic *"What does God say about left-handers?"*. | Cases 1 and reusability | `rank_fan_out()` ranks by content-word overlap with the head query, collapses duplicates by token set, returns the top 3. The full set stays in the report. |

## Known limitations

- **Live capture cannot run on a demo clock.** One query measured **1m36s** against `apify/google-search-scraper`, well past the 75s gate. The committed snapshots are the demo path; live capture is an explicit opt-in.
- **Point-in-time.** All three real captures are `us` / `en` on 2026-08-28 between 15:49 and 15:51 UTC. AI Overviews are volatile, personalised, and not always rendered at all. Re-capture before acting on any of this.
- **Citation URLs are reconstructed, not raw.** Google returns redirect stubs; publisher URLs were recovered by matching against organic results. `url_raw` preserves the original stub for audit. A citation whose publisher is absent from the organic set is flagged unresolved rather than guessed.
- **Brand matching is literal substring matching.** A brand referenced only by nickname, bare domain, or misspelling reads as absent. Counts like "1 of 3" are floors.
- **Only 3 citation cards per overview.** Google attached three to each capture, so `sources_naming_competitor` is a weak denominator. The load-bearing evidence is the overview *text*.
- **The offline judge is a heuristic, not an LLM.** It checks number provenance, token overlap, and structure. It cannot catch a fluent claim that is qualitatively false. `eval_judge.py` uses Anthropic, Gemini, or OpenAI when a key is present; the demo path deliberately does not.
- **Third-party brands.** The Attio rewrite is illustrative copy built from public SERP evidence. It is not Attio-authored or Attio-endorsed.
- **Stock.estate figures are published claims, not verified performance.** Nothing in this repo is investment advice.
- **No outcome measurement.** Nothing here shows a rewrite later earned a citation. That needs a re-capture weeks after publishing and is out of scope.
