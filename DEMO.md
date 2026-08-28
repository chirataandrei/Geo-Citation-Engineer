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

Offline fixture is a sample AI Overview. The requested **competitor** is written into that text if it is missing, so any brand/competitor pair still gets a real GAP stamp. Stats stay from the fixture (not invented). A live SERP for a new query still needs `--live` and `APIFY_TOKEN`.

## Fallback (live run >60s or fail)

- [demo/output/show.html](demo/output/show.html)
- [demo/output/geo-report.md](demo/output/geo-report.md)
