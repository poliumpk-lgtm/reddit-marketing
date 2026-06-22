# Experiments — alternative scraper approaches

These are not the canonical scrapers. The working one lives at
`../reddit_parser.py` (SeleniumBase + UC + CDP). What's here is kept as
a record: each file is a different approach to fetching Reddit search
results, with a different trade-off.

| File | Approach | Status |
|------|----------|--------|
| `reddit_parser_browseruse.py` | LLM agent (`browser-use` + Claude Sonnet) navigates Reddit and returns JSON | **Works**, but expensive: needs `ANTHROPIC_API_KEY`, the `browser-use` Python package, and ~$0.05–0.20 per query in Claude tokens |
| `reddit_parser_playwright.py` | Plain Playwright + `playwright-stealth`, parses the search HTML | **Fails with HTTP 403** against current Reddit anti-bot |

## When each one is worth picking up

**`reddit_parser_browseruse.py`** — when the page layout changes and the
DOM-walking in `reddit_parser.py` breaks. The LLM agent figures out the
new layout on its own (slower, more expensive, but resilient). Useful as
a fallback while you patch the SB scraper.

**`reddit_parser_playwright.py`** — kept for future-proofing. If Reddit
ever loosens its anti-bot, plain Playwright would be the lightest path
(no `uc_driver` download, no `seleniumbase`). Today it returns 403; do
not use it as-is.

## Running them

```bash
# LLM-agent variant
pip install browser-use anthropic
export ANTHROPIC_API_KEY=sk-ant-...
python reddit_parser_browseruse.py

# Plain Playwright variant (will 403)
pip install playwright playwright-stealth
playwright install chromium
python reddit_parser_playwright.py
```

The query and subreddit are hard-coded at the top of each file — edit
the constants directly.

> **Прокси** — эти эксперименты `--proxy` не поддерживают (флаг есть
> только в канонических `../reddit_parser.py` и `../reddit_enrich.py`).
> Если упёрся в Reddit-блок и хочешь обойти через residential —
> вернись к корневым скриптам. Мы крутим их через
> [Proxyma](https://cabinet.proxyma.io/ru/register?ref=bSjpPD1JqgnvpN1f)
> (реферальная ссылка, при регистрации даётся пробный пакет).
> Подойдёт любой residential-провайдер со sticky-сессиями.
