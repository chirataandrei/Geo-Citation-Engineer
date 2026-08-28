# Seed prompt

Paste this into Codex from the repository root.

```text
$geo-citation-engineer

Query: best crm for startups
Brand: Acme
Competitor: HubSpot
Draft: demo/input/draft.md

This is a 2.5 minute demo. Do not open Python source.

1. Run `python demo.py` (Enter between beats) or `python demo.py --auto`.
2. Show the citation GAP from the fetcher, then the rewritten page at demo/output/geo-report.md, then eval pass=true.
3. If Apify is slow, stay offline (default). Prefer `--judge gemini` when GEMINI_API_KEY is set.
```
