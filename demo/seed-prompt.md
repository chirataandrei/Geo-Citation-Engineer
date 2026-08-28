$geo-citation-engineer

Query: best crm for startups
Brand: Acme
Competitor: HubSpot
Draft: demo/input/draft.md

2.5 minute demo. Do not open Python source. Do not pip install. Do not use --live (Apify).

Run: python3 demo.py --auto --judge heuristic

That hits DuckDuckGo HTML (stdlib, no token) for the query above. Change Query / Brand / Competitor / Draft for another company. If the fetch fails, the driver falls back to the bundled fixture.

Show the GAP stamp (brand vs competitor), the GEO rewrite, four bars, PASS, then demo/show.html.

If that fails or takes more than 60 seconds, open demo/output/show.html and demo/output/geo-report.md. Stop.
