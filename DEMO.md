# DEMO — GEO Citation Engineer

Paste [demo/seed-prompt.md](demo/seed-prompt.md) into Codex. 2:00 / 2:30 hard stop.

Query, brand, competitor, and draft come from that file. `python3 demo.py --auto --judge heuristic` reads them. No hardcoded Acme.

## Show

| Clock | On screen |
| --- | --- |
| 0:00–0:20 | AI Overviews cite the competitor, not the brand |
| 0:20–0:50 | GAP stamp: brand **not cited**, competitor **cited** (when that is the fetch result) |
| 0:50–1:30 | GEO page generated from the JSON — stats, list, fan-out H2s |
| 1:30–2:10 | Four bars + **PASS** + HTML board |
| 2:10–2:30 | `$geo-citation-engineer` · MIT |

Default fetch is **DuckDuckGo HTML** (stdlib, no API key). Overview text is extractive snippets — no invented stats. GAP is scored against that live page. `--offline` forces the bundled fixture (competitor name injected if missing). `--live` is Apify Google AI Overview and needs `APIFY_TOKEN` plus pip.

## Fallback (live run >60s or fail)

- [demo/output/show.html](demo/output/show.html)
- [demo/output/geo-report.md](demo/output/geo-report.md)
