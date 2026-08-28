# GEO rewrite rules

Apply these constraints when rewriting first-party content so generative engines can retrieve and cite it. Do not treat them as optional style tips.

Source notes: Aggarwal et al., *GEO: Generative Engine Optimization*, arXiv:2311.09735 (KDD 2024); sentence-level citation studies on AI Overviews.

## Sentence physics

- Target ~10 words per sentence. Hard cap: **15 words**.
- Split anything longer. Never ship a sentence over **18 words**.
- Prefer one atomic fact per sentence. Low syntactic complexity, high semantic density.
- Avoid mid-fluency narrative prose. Either very plain or dense and technical.

## Evidence injection

- Statistics in the first paragraphs raise generative visibility (~40% in GEO studies) **only if the number exists in the fetcher JSON**.
- Direct quotes raise visibility (~41%). Use 6–15 word spans from `quotes[]`. Attribute the reviewer, not the brand marketing team.
- Do not invent percentages, rankings, NPS, or citations.

## Structure

- Convert long paragraphs into labeled lists and H2s. List-like blocks are cited far more often than prose blocks.
- Map each `fan_out` / People Also Ask item to an H2. Generative engines expand the head query; matching only the head term misses retrieval.
- Lead with the citation-gap verdict, then the rewritten page, then a change log.

## First-party leverage

- Most AI citations come from brand-owned pages. Optimize the user's own page rather than chasing third-party roundups.
- Name the brand in an atomic sentence near the top so mention-detection can fire.
- Cite competitor claims only as they appear in `ai_overview_text` or `cited_sources`.

## Forbidden

- Keyword stuffing (GEO paper: no gain, can hurt).
- Fabricated social proof.
- Hedging filler ("it is important to note that…").
- Changing facts that the Apify JSON did not support.
