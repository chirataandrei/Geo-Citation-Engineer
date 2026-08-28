# DEMO.md — run sheet

## What this promises

Paste the seed prompt into Codex from a fresh clone. In under 75 seconds you get:

1. A citation-gap verdict for **`best bible study app`**: YouVersion is named by **3 of 8** captured sources, **Bible Chat by 0**.
2. A rewritten page section at `output/geo-report.bible-chat.md`, every fact traced to an evidence field.
3. A pass/fail table from two independent evals: deterministic GEO compliance and an offline heuristic RAG-triad judge.

No credentials. No network. Nothing to install beyond Python 3.11+.

## Prerequisites

Python 3.11+ on PATH. That is all. `pip install -r requirements.txt` is **not** required for the demo path — the scripts on the demo path use only the standard library. The requirements file exists for optional live Apify capture and optional LLM judges.

## Run it

```bash
git clone <repo> && cd Geo-Citation-Engineer
```

Then in Codex, paste the contents of [`demo/seed-prompt.md`](demo/seed-prompt.md).

## Or run it without an agent

Three commands, ~0.5s total:

```bash
python .agents/skills/geo-citation-engineer/scripts/run_geo.py plan --brief demo/input/bible-chat.brief.json
```

```bash
python .agents/skills/geo-citation-engineer/scripts/run_geo.py score --brief demo/input/bible-chat.brief.json --out-dir demo/output
```

The second command scores the **committed** rewrite in `demo/output/`, so it passes even if no agent has written anything yet.

The test suite is optional and is the only thing here that needs a dependency:

```bash
python -m pip install pytest && python -m pytest -q
```

Neither the seed prompt nor the two commands above import pytest, so a laptop without it still runs the full demo.

## Expected output

`plan` prints:

```
"gap_verdict": "competitor cited; brand absent"
"evidence_level": "sufficient"
"action": "rewrite"
"sources_naming_competitor": 3
"sources_total": 8
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
| Finished report + rewrite + change log | [`demo/output/geo-report.bible-chat.md`](demo/output/geo-report.bible-chat.md) |
| Merged evidence the evals scored against | [`demo/output/evidence.bible-chat.json`](demo/output/evidence.bible-chat.json) |
| Cross-industry run, no code edits | [`demo/output/geo-report.attio.md`](demo/output/geo-report.attio.md) |
| Correctly refused (brand already cited) | [`demo/output/geo-report.youversion-already-cited.md`](demo/output/geo-report.youversion-already-cited.md) |
| Correctly refused (evidence too thin) | [`demo/output/geo-report.thin-evidence.md`](demo/output/geo-report.thin-evidence.md) |
| Eval results | [`demo/evals.md`](demo/evals.md) |

## 2-minute demo script

- **0:00** The problem, in one line. For `best bible study app`, 3 of 8 sources Google surfaces name YouVersion. Zero name Bible Chat. If you are not in the citable set, no AI answer can cite you.
- **0:20** Show `demo/input/snapshots/best-bible-study-app.2026-08-28.json`. Real capture, real request URL, real retrieval timestamp, and an honest note that no AI Overview rendered.
- **0:35** Run `plan`. Point at `action: rewrite` and at `allowed_numbers`, split into what the brand may claim versus what belongs to third parties.
- **1:00** Show the rewrite and the change log. Every row names the evidence field behind it.
- **1:20** Run `score`. Two independent evals, both green, invented numbers empty.
- **1:40** The part that matters: swap the brand to YouVersion — already cited — and the skill **refuses** to write. Same for thin evidence. It will not manufacture a gap.
- **1:55** Same skill, zero edits, different industry: `demo/output/geo-report.attio.md`.

## Timing

Measured on the demo path, Python 3.13, cold:

| Command | Time |
|---------|------|
| `plan` | ~0.17s |
| `score` | ~0.19s |
| `pytest` (18 tests, optional) | ~0.13s |

Agent turns dominate the 75s budget, not the scripts. That is why the workflow is two commands and one edit, with the writing rules printed by `plan` so no extra file read is needed.
