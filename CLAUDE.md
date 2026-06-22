# CLAUDE.md

Notes for Claude Code working in this repo.

## What this project is

A toolkit for fetching Reddit data + an opinionated lead-gen pipeline
template built on top of it. Three layers:

1. **Core scrapers** at the repo root: `reddit_parser.py` (SeleniumBase
   search-page scraper with upvotes/comments), `reddit_rss.py` (stdlib
   Atom-feed fetcher), `reddit_enrich.py` (per-permalink upvote/comment
   enricher).
2. **`experiments/`** — alternative scrapers (LLM agent via
   `browser-use`, plain Playwright + stealth). Kept for reference; the
   plain-Playwright one currently 403s against Reddit's anti-bot.
3. **`example-leadgen/`** — a template orchestrator that does
   RSS → score → bucket → enrich → xlsx with a feedback loop. Generic;
   the user fills `SUBS`, `scoring.yml`, `entities.yml`, `voice/`.

The user-facing docs are `README.md` (root), `experiments/README.md`,
`example-leadgen/README.md`. Read those before touching code.

## Repo layout

```
.
├── reddit_parser.py            # canonical SB search scraper
├── reddit_rss.py               # generic Atom fetcher
├── reddit_enrich.py            # per-permalink enricher
├── requirements.txt            # just `seleniumbase`
├── experiments/
│   ├── reddit_parser_browseruse.py   # LLM-agent variant (works, expensive)
│   └── reddit_parser_playwright.py   # plain Playwright + stealth (403s)
└── example-leadgen/
    ├── orchestrator.py          # scan / sync-overrides / sync-voice
    ├── scoring.yml              # placeholder rubric
    ├── entities.yml             # placeholder entity registry
    ├── fill_replies.py          # bulk-fill Suggested Reply column
    ├── replay_from_json.py      # offline xlsx rebuild
    └── voice/
        ├── rules.md             # house-style guidance
        ├── lessons.jsonl        # append-only feedback log (empty)
        └── examples.jsonl       # few-shot examples (empty)
```

## Anti-bot context (important)

Reddit's edge gates listing/search endpoints behind a JS challenge that
appends `?solution=...&js_challenge=1&token=...`. Five out of six common
approaches fail with HTTP 403:

- `urllib` / `requests` with any UA → 403
- Playwright headless (with or without `playwright-stealth`) → 403
- Two-stage cookie warming + in-page `fetch()` for `/search.json` → 403

Only **SeleniumBase `SB(uc=True)` + `activate_cdp_mode`** works. Don't
"simplify" `reddit_parser.py` or `reddit_enrich.py` to plain Playwright
— they will start failing.

The `.json` endpoints (`/search.json`, `<permalink>.json`) all 403 too,
even from real Chrome with cookies. They want a logged-in session or a
registered OAuth app.

**Per-IP escalation is real.** After ~5–10 SB sessions in a short window
from one IP, Reddit upgrades from JS challenge to hard block (response
body: *"You've been blocked by network security…"*). Cooldown is
6–24 hours. Both scrapers accept a `--proxy "user:pass@host:port"`
flag — pass a sticky-session residential proxy when running at any
volume. Empirically this restores access immediately.

**Beware leaked creds.** SeleniumBase auto-generates a Chrome extension
under `downloaded_files/proxy_ext_dir/` containing the proxy username
and password in plaintext (`background.js`). The repo's `.gitignore`
excludes `downloaded_files/`, but if a contributor commits that
directory by accident, creds leak. If you see it staged, refuse the
commit.

## DOM extraction is layout-dependent

Reddit's search results no longer use `<shreddit-post>`. The current
`reddit_parser.py` extracts by:

1. Restricting to `[role="main"]` so sidebar recommendations don't leak.
2. Matching `/r/<sub>/comments/<id>/<slug>` with a regex.
3. Walking up the DOM (≤10 levels) to find a `<faceplate-number>` whose
   surrounding span text contains "vote".

If the layout changes, the symptom is empty results despite the page
loading. The diagnostic snippet from the README (dump every
`<faceplate-number>` with its parent `outerHTML`) is the right first
step before patching.

## When the user asks to extend `example-leadgen/`

The template was anonymized from a real proxy/scraping lead-gen pipeline.
Anything category-specific (proxy keywords, competitor names, sneaker
use-case detection in `Scorer._detect_use_cases`, etc.) was either
genericized or left as a placeholder. If you're adding niche-specific
rules, put them in the user's YAML — don't hard-code them back into
`orchestrator.py`. Exception: `Scorer._detect_use_cases` is currently
a hard-coded list of regex; if the user wants different use cases,
either edit that method directly or refactor it to read from
`scoring.yml`.

## Subprocess plumbing

`orchestrator.py` shells out to `../reddit_rss.py` and `../reddit_enrich.py`
(at the repo root, one level up from `example-leadgen/`). Paths are
computed via `HERE.parent`. If the orchestrator gets moved, update those.

`reddit_enrich.py`'s stdout is mixed with seleniumbase framework noise.
The orchestrator finds the JSON blob with `re.search(r"\n\[\s*\n",
proc.stdout)` — fragile but works in practice. If enrich starts failing
with "failed to parse stdout", that regex is the suspect.

## Don't recreate this stuff

- The project's original brand-specific config (a now-removed
  brand-named config folder, a Russian-language sample report, hard-coded
  competitor lists) — deliberately scrubbed during anonymization. If the
  user asks for "the original setup" it's gone; treat the template as
  the canonical state.
- `.venv-reddit/`, `node_modules/`, Playwright source files — this repo
  used to live inside a Playwright fork. All of that was deleted.
- Sample CSV/XLSX/JSON outputs — none committed; user generates them.

## Testing

There are no tests. Smoke tests are in the root README's "Reproducing
from zero" section. The user's expected verification path:

```bash
python reddit_parser.py --subreddit MachineLearning --query "transformers" --time week
python reddit_rss.py --subreddit MachineLearning --feed top --time week --limit 5
cd example-leadgen && python orchestrator.py scan  # exits 1 with "SUBS is empty"
```

If you change scraper internals, run those three by hand before claiming
done. The first one needs `seleniumbase` installed and downloads
`uc_driver` on first run (~10MB, takes ~30s).
