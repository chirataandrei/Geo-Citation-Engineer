# Evals

The skill must prove two things: the rewrite is GEO-shaped, and every injected fact is grounded in the Apify (or fixture) JSON.

## Commands

From the repository root:

```bash
source .venv/bin/activate
python -m pytest -q
```

Expected: all tests pass.

Deterministic GEO compliance (no LLM):

```bash
python .agents/skills/geo-citation-engineer/scripts/geo_compliance.py \
  --rewrite demo/output/geo-report.md \
  --source demo/output/serp.json
```

Expected: `"pass": true`, `geo_compliance_score` 1.0.

RAG triad (Gemini if `GEMINI_API_KEY` is set):

```bash
python .agents/skills/geo-citation-engineer/scripts/eval_judge.py \
  --judge gemini \
  --query "best crm for startups" \
  --rewrite demo/output/geo-report.md \
  --source demo/output/serp.json \
  --original-draft demo/input/draft.md
```

Expected: `"judge": "gemini"`, `"pass": true`, groundedness 1.0.

Offline / no API key:

```bash
python .agents/skills/geo-citation-engineer/scripts/eval_judge.py \
  --offline \
  --query "best crm for startups" \
  --rewrite demo/output/geo-report.md \
  --source demo/output/serp.json \
  --original-draft demo/input/draft.md
```

Stage driver (runs fetch + compliance + judge):

```bash
python demo.py --auto
```

## What is measured

| Check | Type | Fail if |
| --- | --- | --- |
| Sentence cap (target ≤15, hard ≤18 words) | deterministic | any sentence over 18 words |
| List structure | deterministic | no markdown list |
| Sourced statistic | deterministic | rewrite invents a number absent from JSON |
| Quote present when G2 quotes exist | deterministic | quotes in JSON unused |
| Context relevance | LLM-as-a-judge | source JSON does not address the query |
| Groundedness | LLM-as-a-judge | unsourced claims or invented stats |
| Answer relevance | LLM-as-a-judge | rewrite ignores GEO structure or the GTM ask |

Judge order: Anthropic → Gemini → OpenAI → heuristic. `--judge gemini` forces Gemini.

A golden rewrite lives at [demo/output/geo-report.md](output/geo-report.md). The losing draft is [demo/input/draft.md](input/draft.md).
