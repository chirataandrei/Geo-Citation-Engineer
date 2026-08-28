# DEMO.md — run sheet

## What this promises

Paste the seed prompt into Codex from a fresh clone. In well under 75 seconds you get:

1. A citation-gap verdict for **`best real estate crowdfunding platform europe`**: Google's own AI Overview names **EstateGuru**, InRento, Reinvest24 and Raizers. It never names **Stock.estate**.
2. A rewritten page section at `output/geo-report.stock-estate.md`, every fact traced to an evidence field.
3. A pass/fail table from two independent evals: deterministic GEO compliance and an offline heuristic RAG-triad judge.

**No credentials. No network. Nothing to install.** The demo path uses only the Python standard library.

## Prerequisites

Python 3.11+ on PATH. That is all.

`pip install -r requirements.txt` is **not** required for the demo. Those dependencies exist only for optional live Apify capture and optional LLM judges.

## Run it

```bash
git clone <repo> && cd Geo-Citation-Engineer
```

Then in Codex, paste the contents of [`demo/seed-prompt.md`](demo/seed-prompt.md).

## Or run it without an agent

Two commands, ~0.4s total:

```bash
python .agents/skills/geo-citation-engineer/scripts/run_geo.py plan --brief demo/input/stock-estate.brief.json
```

```bash
python .agents/skills/geo-citation-engineer/scripts/run_geo.py score --brief demo/input/stock-estate.brief.json --out-dir demo/output
```

The second command scores the **committed** rewrite in `demo/output/`, so it passes even if no agent has written anything yet.

The test suite is optional and is the only thing here needing a dependency:

```bash
python -m pip install pytest && python -m pytest -q
```

## Expected output

`plan` prints:

```
"gap_verdict": "competitor cited; brand absent"
"competitor_named_in_ai_overview": true
"brand_named_in_ai_overview": false
"opportunity": "competitor_gap"
"action": "rewrite"
```

`score` prints:

```
"geo_compliance": { "score": 1.0, "pass": true }
"judge": { "scores": {"context_relevance": 1.0, "groundedness": 1.0, "answer_relevance": 1.0}, "pass": true }
"pass": true
```

## Fallback if anything goes wrong on stage

Every artifact is committed and complete. Open these directly:

| Show | Path |
|------|------|
| Finished report + rewrite + change log | [`demo/output/geo-report.stock-estate.md`](demo/output/geo-report.stock-estate.md) |
| The live AI Overview it was built from | [`demo/input/snapshots/best-real-estate-crowdfunding-platform-europe.2026-08-28.json`](demo/input/snapshots/best-real-estate-crowdfunding-platform-europe.2026-08-28.json) |
| Cross-industry run, no code edits | [`demo/output/geo-report.attio.md`](demo/output/geo-report.attio.md) |
| Uncontested-answer run | [`demo/output/geo-report.formidable-builders.md`](demo/output/geo-report.formidable-builders.md) |
| Correctly refused (brand already cited) | [`demo/output/geo-report.estateguru-already-cited.md`](demo/output/geo-report.estateguru-already-cited.md) |
| Correctly refused (evidence too thin) | [`demo/output/geo-report.thin-evidence.md`](demo/output/geo-report.thin-evidence.md) |
| Eval results and the defects they caught | [`demo/evals.md`](demo/evals.md) |

## 2-minute demo script

- **0:00 — The problem, in Google's words.** Read the captured AI Overview aloud: *"The top-rated real estate crowdfunding platforms in Europe include Estateguru… InRento… BrikkApp."* Stock.estate is a regulated European platform doing exactly this, and Google does not mention it. You cannot be recommended by an answer you are not in.
- **0:20 — The evidence is real.** Open the snapshot. Actor, request URL, retrieval timestamp, verbatim overview text, and an honest `post_processing` list saying exactly what was trimmed and how the redirect URLs were resolved.
- **0:40 — Run `plan`.** Point at `competitor_named_in_ai_overview: true` / `brand_named_in_ai_overview: false`, and at `allowed_numbers`, split into what Stock.estate may claim versus what belongs to third parties. Stock.estate may say "from 100 EUR". It may not say "6% to 11%" — that is InRento's number, quotable only with InRento named.
- **1:05 — The rewrite and change log.** Every row names the evidence field behind it.
- **1:20 — Run `score`.** Two independent evals, both green, invented numbers empty.
- **1:35 — The part that matters: it refuses.** Swap the brand to EstateGuru on the *same snapshot* and it declines — already cited, nothing to close. Thin evidence aborts. And on `open source agent skills`, where nobody is named, it reports an *uncontested answer* instead of inventing a competitor.
- **1:55 — Same skill, zero edits, different industry:** `demo/output/geo-report.attio.md`.

## Timing

Measured on this machine, Python 3.13:

| Command | Time |
|---------|------|
| `plan` | ~0.17s |
| `score` | ~0.19s |
| `plan` + `score` from a fresh clone | **0.32s** |
| `pytest` (22 tests, optional) | ~0.1s |
| Live Apify capture, one query | **1m36s** — why it is off the demo path |

Agent turns dominate the 75s budget, not the scripts. That is why the workflow is two commands and one edit, with the writing rules printed by `plan` so no extra file read is needed.

## Live capture (optional, not on the demo path)

One query took 1m36s, which alone exceeds the 75s gate. Do not run this on stage.

```bash
cp .env.example .env    # set APIFY_TOKEN
pip install -r requirements.txt
python .agents/skills/geo-citation-engineer/scripts/apify_fetcher.py \
  --query "best real estate crowdfunding platform europe" \
  --brand "Stock.estate" --competitor "EstateGuru" --out output/serp.json
```

Then point a brief's `snapshot` at `output/serp.json`. Without a token the fetcher exits non-zero and says to use a snapshot — that is the graceful degradation, not a failure.
