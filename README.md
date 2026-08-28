# GEO Citation Engineer

Agent skill for [Generative Engine Optimization](https://agentskills.io/specification). It finds when Google AI Overviews cite a competitor and not your brand, rewrites first-party copy so models can quote it, and proves the rewrite with evals.

Track: **ai-search-optimization**. MIT.

## Demo

Paste [demo/seed-prompt.md](demo/seed-prompt.md) into Codex. That is the whole run.

```bash
python3 demo.py --auto --judge heuristic
```

The driver reads Query, Brand, Competitor, and Draft from [demo/seed-prompt.md](demo/seed-prompt.md). Change those lines (or pass `--brand` / `--competitor`) for another company. Default search is DuckDuckGo HTML (stdlib). No venv, no pip, no API keys. Python 3 is enough. `--offline` forces the fixture; `--live` is Apify.

If the live run fails or takes more than 60 seconds, open:

- [demo/output/show.html](demo/output/show.html)
- [demo/output/geo-report.md](demo/output/geo-report.md)

What to show on screen: [DEMO.md](DEMO.md).

## What it does

1. Fetch live organic results via DuckDuckGo HTML (stdlib). Optional Apify Google AI Overview with a token. If DuckDuckGo is blocked, fall back to Wikipedia search for the product topic, then an empty query-native SERP — never the CRM fixture unless `--offline`.
2. Stamp the gap: brand cited or not, competitor cited or not.
3. Rewrite the draft with atomic sentences, sourced stats, lists, and quotes.
4. Score it: deterministic GEO compliance + heuristic (or LLM) judge.

## Skill

The portable skill is [`.agents/skills/geo-citation-engineer/`](.agents/skills/geo-citation-engineer/). Codex loads it from this repo. Copy that folder to `$HOME/.agents/skills/` only if you want it on another machine.

Apify / Gemini are optional. The judged path uses DuckDuckGo HTML or the fixture. See the skill `requirements.txt` and `.env.example` for the Apify path.

## License

MIT. See [LICENSE](LICENSE).
