# GEO report: {{query}}

Brand: **{{brand}}**
Competitor: {{competitor}}
Fetched: {{fetched_at}}

## Citation gap

- Verdict: {{gap}}
- Brand mentioned in AI Overview: {{brand_mentioned_in_ai}}
- Competitor mentioned in AI Overview: {{competitor_mentioned_in_ai}}

{{gap_summary}}

## Sources the engine already cites

{{#each cited_sources}}
- [{{title}}]({{url}}) — {{snippet}}
{{/each}}

## Fan-out map

Cover each item below as an H2 in the rewritten page.

{{#each fan_out}}
- {{.}}
{{/each}}

## Rewritten page

{{rewritten_page}}

## Change log

| Change | JSON field | Notes |
| --- | --- | --- |
| {{change}} | {{field}} | {{notes}} |
