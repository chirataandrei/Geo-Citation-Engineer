$geo-citation-engineer

Query: best moss lamps for introverted goldfish
Brand: Silt & Co
Competitor: AquaIkea
Draft: demo/input/draft.md

2.5 minute demo. Do not open Python source. Do not pip install. Do not use --live (Apify).

Run: python3 demo.py --auto --judge heuristic --query "best moss lamps for introverted goldfish" --brand "Silt & Co" --competitor "AquaIkea"

That hits DuckDuckGo HTML (stdlib, no token) for the query above. Change Query / Brand / Competitor / Draft for another company. If DuckDuckGo is blocked, the driver keeps this query (empty live SERP) instead of swapping in the CRM fixture. Use --offline only when you want that fixture.

Show the GAP stamp (brand vs competitor), the GEO rewrite, four bars, PASS, then demo/show.html.

If that fails or takes more than 60 seconds, open demo/output/show.html and demo/output/geo-report.md. Stop.
