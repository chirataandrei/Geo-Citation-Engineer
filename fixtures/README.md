# fixtures/ — synthetic unit-test data only

**Nothing in this directory is web evidence, and none of it may be presented as a real capture.**

These files are hand-authored inputs for `tests/test_geo.py`. They use the deliberately
non-existent brand name "Acme" as a negative control: a brand that must never match
anything. Real, sourced evidence lives in
[`demo/input/snapshots/`](../demo/input/snapshots/), where every file carries a
`provenance` block with its request URL and retrieval timestamp.

| File | Purpose |
|------|---------|
| `serp_raw.json` | Exercises `normalize_serp_item()` against the `apify/google-search-scraper` item shape. |
| `serp_sample.json` | Pre-normalized payload for compliance and judge unit tests. |
| `g2_sample.json` | Exercises `quotes_from_reviews()` ranking and quote clipping. |
| `draft.md` | A weak draft, input to the pairwise judge test. |
| `rewrite.md` | A compliant rewrite; asserted to pass. |
| `rewrite_bad.md` | An overlong, unsourced rewrite; asserted to fail. |

The demo path does not read this directory. `run_geo.py` reads briefs from
`demo/input/` only.
