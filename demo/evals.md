# Evals

Every result below was produced by running the commands shown, on commit HEAD of this branch, Python 3.13.9, Windows 11. No credentials, no network. Reproduce with:

```bash
python -m pytest -q
```

## The three cases

| # | Case | Input | What correct behaviour is | Observed result | Pass/Fail |
|---|------|-------|---------------------------|-----------------|-----------|
| 1 | **Intended use** — gap exists, rewrite warranted | `demo/input/bible-chat.brief.json` — real capture for `best bible study app`, brand Bible Chat, competitor YouVersion | Detect that the competitor is in the citable set and the brand is not. Produce a rewrite. Both evals green, zero invented numbers. | `action: rewrite`, `gap_verdict: "competitor cited; brand absent"`, `sources_naming_competitor: 3` of `8`. Compliance `1.0`, `pass: true`. Judge `context 1.0 / groundedness 1.0 / answer 1.0`, `pass: true`. `invented_numbers: []`. | **Pass** |
| 2 | **Insufficient evidence** — must refuse to claim a gap | `demo/input/thin-evidence.brief.json` — labelled test fixture: one thin source, no AI Overview, no numeric facts | Refuse. Do not assert a citation gap. Do not rewrite. Do not go hunting for more evidence. | `evidence_level: insufficient`, `action: abort`, reason `"Only 1 cited source(s) and no AI Overview text."` Report written with an explicit no-rewrite outcome; `scored: false`. No rewrite produced. | **Pass** |
| 3 | **Failure / exclusion** — brand already cited, rewrite would be wasted work | `demo/input/youversion-already-cited.brief.json` — the *same real snapshot* as case 1 with brand and competitor swapped | Recognise the brand is already inside the citable set and decline. There is no gap to close. | `gap_verdict: "brand cited; competitor absent"`, `action: decline`, reason `"Brand is already inside the citable set … no rewrite is warranted."` No rewrite produced. | **Pass** |

Case 3 shares its evidence file with case 1 deliberately. It proves the verdict is computed from the evidence rather than assumed from the request: the same snapshot yields "rewrite" for one brand and "decline" for another.

## Reusability check

Different industry, different brand, different competitor, **zero code or skill edits** — only a new brief pointing at a new snapshot.

| Case | Input | Observed result | Pass/Fail |
|------|-------|-----------------|-----------|
| Cross-industry run | `demo/input/attio.brief.json` — real capture for `best crm for startups`, brand Attio, competitor HubSpot | `action: rewrite`, `gap_verdict: "competitor cited; brand absent"`. `allowed_numbers.brand` is empty because no first-party facts were collected, so the rewrite degraded to qualitative claims with every digit attributed to its publisher. Compliance `1.0`, judge `1.0 / 1.0 / 1.0`, `invented_numbers: []`. | **Pass** |

## Defects these evals actually caught

An all-green table on the first run would mean the evals were not doing any work. These are real failures found and fixed while building, each reproducible by reverting the named change.

| Defect | How it surfaced | Fix |
|--------|-----------------|-----|
| The two evals contradicted each other. `geo_compliance` passed the Bible Chat rewrite at `1.0` while the heuristic judge returned `groundedness: 0.0` and flagged all 7 first-party numbers as invented. | Case 1 | `eval_judge._blob()` did not include `brand_facts.claims` in its evidence blob, so legitimate first-party facts looked unsourced. Added the claims (and `organic`) to the blob. |
| `40M` contributed no usable number, so a rewrite saying "40 million" would have been scored as inventing `40`. | Case 1 | `NUMBER_RE` required a trailing `\b`, which `40M` does not have. Dropped the trailing boundary so source and rewrite extract symmetrically. |
| A competitor's star rating (`4.7`) and review count (`131,826`) were offered in the same allow-list as the brand's own metrics, inviting a rewrite that claimed them for the brand. | Case 1 | Split the fact budget into `allowed_numbers.brand` (assertable) and `allowed_numbers.evidence` (quotable only with the source named in the sentence). |
| Re-running `plan` silently overwrote the committed fallback output, destroying the artifact the demo depends on. | Discovered on a second run of case 1 | `--out-dir` now defaults to the gitignored `output/`; `demo/output/` is written only when explicitly targeted. |
| Nine fan-out questions were handed to the agent for H3 coverage, including the genuinely captured but off-topic `"What does God say about left-handers?"`, and three near-duplicate free-CRM queries. | Cases 1 and reusability | Added `rank_fan_out()`: rank by content-word overlap with the head query, collapse duplicates by token set, return the top 3 as `fan_out_priority`. Full set stays in the report. |

## Known limitations

- **No AI Overview text in either real snapshot.** Google does not render AI Overviews to automated browser sessions, and the judging laptop has no Apify credentials. Both snapshots record `ai_overview_present: false` and an explicit note. The gap is therefore measured against the organic citable set — the corpus AI answers ground on — not verbatim AI Overview text. Live overview capture requires `APIFY_TOKEN`.
- **Brand matching is literal substring matching.** A brand referenced only by nickname, bare domain, or misspelling will read as absent. Case 1's `3 of 8` is a floor, not a precise count.
- **The offline judge is a heuristic, not an LLM.** It checks number provenance, token overlap, and structure. It cannot catch a fluent claim that is qualitatively false. `eval_judge.py` will use Anthropic, Gemini, or OpenAI when a key is present; the demo path deliberately does not.
- **Point-in-time.** Both captures are `us` / `en` on 2026-08-28. AI answers are volatile and personalised.
- **No outcome measurement.** Nothing here shows the rewrite later earned a citation. That needs a re-capture weeks after publishing and is out of scope.
- **Snapshots are top-of-page only.** Pagination was not followed.
