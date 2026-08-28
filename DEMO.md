# DEMO — GEO Citation Engineer

2.5-minute run sheet for the GTM Skillathon. Repo root, venv on.

## Setup (before the slot)

```bash
cd ~/Documents/geo-citation-engineer
source .venv/bin/activate
```

Optional: `APIFY_TOKEN` for live fetch, `GEMINI_API_KEY` for the Gemini judge.

## Seed

Paste [demo/seed-prompt.md](demo/seed-prompt.md) into Codex, or run the stage driver:

```bash
python demo.py
```

Press Enter between beats. The last beat writes [demo/show.html](demo/show.html) and opens it — glance at that board on the second screen.

Hands-free:

```bash
python demo.py --auto --judge gemini
```

CI / no browser:

```bash
python demo.py --auto --judge heuristic --no-web
```

If Apify is slow, do **not** pass `--live`. Offline fixtures use the same JSON contract.

## Beats

| Time | Show | File |
| --- | --- | --- |
| 0:00–0:20 | Problem: AI Overviews cite HubSpot, not Acme | speak |
| 0:20–0:40 | Losing GTM copy (INVISIBLE) | [demo/input/draft.md](demo/input/draft.md) |
| 0:40–1:20 | GAP stamp: Acme not cited, HubSpot cited | fetcher / `demo.py` beat 2 |
| 1:20–1:50 | GEO rewrite (atomic sentences, 64%, list, G2 quote) | [demo/output/geo-report.md](demo/output/geo-report.md) |
| 1:50–2:25 | Four score bars + PASS, then the HTML board | [demo/show.html](demo/show.html) |
| 2:25–2:30 | `$geo-citation-engineer` · MIT · forkable | close |

## Do not

- Open `apify_fetcher.py` or other script source
- Run pytest on stage
- Debug a hung Actor — fall back to `--offline`

## Success criteria

Judges see the citation **gap**, four full bars, **PASS**, and the dark HTML board with current page vs GEO page.
