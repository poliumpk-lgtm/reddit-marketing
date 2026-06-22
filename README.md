# Reddit lead-gen toolkit

Three layers, take what you need:

1. **Core scrapers** — `reddit_parser.py`, `reddit_rss.py`, `reddit_enrich.py`.
   Standalone Python scripts to pull Reddit search results, RSS feeds, and
   per-permalink upvote/comment counts. Built to survive Reddit's anti-bot.
2. **`experiments/`** — alternative scraper approaches that mostly fail
   against Reddit's edge. Kept as a record of what doesn't work and why.
3. **`example-leadgen/`** — opinionated template for a full lead-gen
   pipeline on top of the core scrapers: RSS → score → bucket → enrich
   → xlsx with manual-review columns → feedback loop. Bring your own
   subs, scoring rubric, and voice.

Use just the core if you want a Reddit fetcher. Adopt `example-leadgen/`
if you're doing community-driven outbound and want classification +
draft-tracking out of the box.

## Quick start (core only)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Search a sub via the SeleniumBase scraper (returns title/upvotes/url)
python reddit_parser.py --subreddit MachineLearning --query "transformer scaling" --time month

# Pull an RSS feed (no Chromium, stdlib only)
python reddit_rss.py --subreddit LocalLLaMA --feed top --time week --limit 25

# Enrich a list of permalinks with upvotes + comment counts
echo '[{"url":"https://www.reddit.com/r/LocalLLaMA/comments/<id>/<slug>/"}]' \
  | python reddit_enrich.py
```

First run downloads `uc_driver` (~10 MB) automatically into the seleniumbase
package directory. Subsequent runs skip this. A short-lived Chromium window
opens during SB runs; close it manually only if it hangs.

## What each core script does

| File | Purpose |
|------|---------|
| `reddit_parser.py` | Full search-page DOM scraper via SeleniumBase. Returns `{title, upvotes, url}`. |
| `reddit_rss.py` | Lightweight Atom-feed fetcher with pagination + body extraction. stdlib only, no Chromium. No score. |
| `reddit_enrich.py` | Reads `[{url}, ...]` JSON on stdin, walks each permalink with SB and adds upvotes+comments. Bridge between RSS and full data. |
| `requirements.txt` | Python deps (just `seleniumbase`). `reddit_rss.py` needs nothing extra. |

**Pick the right tool:** if you need upvote/comment counts → `reddit_parser.py`.
If you only need titles + permalinks + timestamps + author + body text →
`reddit_rss.py` (10× faster, no browser, polls cleanly). For a hybrid
pipeline see [example-leadgen/README.md](example-leadgen/README.md).

## Why SeleniumBase, not <thing-X>

Six approaches were tried. Five fail with HTTP 403 ("blocked by network
security"); only one works.

| Approach | Result |
|---|---|
| `urllib` with script User-Agent | 403 |
| `urllib` with browser User-Agent | 403 |
| `requests` with browser UA + `Accept`/`Accept-Language` | 403 |
| Playwright headless Chromium | 403 |
| Playwright headless + `playwright-stealth` | 403 |
| Two-stage: warm cookies on `/r/<sub>/`, in-page `fetch()` for `/search.json` | 403 |
| **SeleniumBase `SB(uc=True)` + `activate_cdp_mode`** | **works** |

Reddit's edge specifically gates the listing/search endpoints behind a JS
challenge that ends up appending `?solution=...&js_challenge=1&token=...` to
the URL. The undetected-chromedriver build that SeleniumBase ships solves
this transparently.

### What CDP is and why we need it

**CDP = Chrome DevTools Protocol.** It's the native WebSocket+JSON-RPC
protocol Chrome speaks to its own DevTools (the panel that opens on F12).
Anyone connected to a running Chrome's debugging port has full control:
open URLs, run JS, read DOM, intercept network. Same protocol Puppeteer
and Playwright are built on.

The reason it matters here: there are **two independent layers** of
anti-bot detection, and we need to defeat both:

| Layer | Vanilla setup | What we use |
|-------|---------------|-------------|
| **Which browser binary** runs | stock Chromium → fingerprintable as automated | `uc=True` → undetected-chromedriver, patches out telltale signals like `navigator.webdriver` |
| **How we drive it** | Selenium WebDriver → ChromeDriver injects extra signals into the page | `activate_cdp_mode(url)` → talk to Chrome directly over CDP, no WebDriver layer |

Either one alone fails: stock Chromium with CDP gets fingerprinted; UC
Chromium driven via WebDriver leaks WebDriver signals. The combination
is what gets through Reddit's JS challenge.

In practice this means the working scrapers all have the same shape:

```python
with SB(uc=True, test=True, locale_code="en") as sb:
    sb.activate_cdp_mode(url)         # switch from WebDriver to raw CDP
    sb.cdp.scroll_down(1000)          # CDP: Input.dispatchMouseEvent
    sb.cdp.evaluate(extract_js)       # CDP: Runtime.evaluate
```

One quirk to remember: `sb.cdp.evaluate(...)` returns a CDP `RemoteObject`
reference for non-primitive return values, which round-trips to Python
as `{}`. Always wrap the JS in `JSON.stringify(...)` and `json.loads`
on the Python side. The shipped scrapers already do this; if you write
new extraction code, follow the pattern.

Two related dead ends, documented just so we don't re-walk them:

- The Reddit JSON endpoints (`/r/<sub>/search.json`, `.json` on any
  permalink) all return 403 — even from inside a real Chrome with cookies.
  They want a logged-in session or a registered OAuth app.
- `old.reddit.com` is blocked by some corporate/network-level filters
  ("This site is blocked by your organization's policy"). SeleniumBase's
  local Chromium ignores org policy because it runs as a separate browser
  instance.

## How `reddit_parser.py` extraction works

Reddit's search results page **no longer uses `<shreddit-post>`**. Each
result is rendered as a row inside `[role="main"]` containing:

- An `<a href="/r/<sub>/comments/<id>/<slug>/">` whose text is the title.
- A nearby footer with two `<faceplate-number number="N">` elements
  wrapped in spans — the first labeled "X votes", the second "X comments".

The script extracts by:

1. Restricting to anchors inside `[role="main"]` so sidebar
   recommendations don't leak in.
2. Matching `/r/<sub>/comments/<id>/<slug>` with a regex that strips
   trailing slashes/query/fragments.
3. Walking up the DOM (≤10 levels) to find a `<faceplate-number>` whose
   surrounding span text contains "vote".

If Reddit changes the layout, the early symptom will be empty results
despite the page title showing the search ran. Diagnostic snippet:

```python
sb.cdp.evaluate("""
JSON.stringify(Array.from(document.querySelectorAll('faceplate-number[number]'))
  .map(el => ({ number: el.getAttribute('number'),
                ctx: el.parentElement?.outerHTML.slice(0, 180) })))
""")
```

Drop that into `main()` after the scroll/sleep block to inspect what's
actually on the page.

## Known quirks

- **Some posts show 0 votes.** This is what Reddit actually displays in
  search results for those posts. It's not a parser bug. Visiting the
  permalink shows the real score; if you need that, run `reddit_enrich.py`
  on the URLs.
- **~25 results per run.** Reddit's search returns one page; the script
  doesn't paginate. Add `sb.cdp.scroll_down(...)` loops + dedup if you
  need more — the script already dedups by permalink.
- **`sb.cdp.evaluate` swallows complex object returns.** Returning a
  raw JS object yields `{}` on the Python side. Always wrap the return
  value in `JSON.stringify(...)` and parse on the Python side.
- **Windows pop briefly.** UC mode runs Chromium headfully. Don't
  dismiss the window manually mid-run — the script closes it on exit.

## Reddit IP blocks (and how to get around them)

After ~5–10 SB sessions in a short window from one IP, Reddit's edge
upgrades from "JS challenge" to a hard block on permalink and listing
pages. The body of the response says literally:

> *"You've been blocked by network security. To continue, log in to your
> Reddit account or use your developer token."*

This is **per-IP**, not per-fingerprint. The undetected-chromedriver in
`SB(uc=True)` does its job — Reddit just doesn't trust your IP anymore.
Cooldown is typically 6–24 hours.

Three ways out:

1. **Wait it out.** Cheapest and you don't lose anything.
2. **Change network.** Mobile tethering, VPN to another country.
   Datacenter VPNs (NordVPN, ProtonVPN) are themselves often pre-flagged
   on Reddit; residential VPNs work better.
3. **Route SB through a residential proxy.** Both `reddit_parser.py`
   and `reddit_enrich.py` accept a `--proxy` flag:

   ```bash
   python reddit_parser.py \
     --subreddit MachineLearning --query "transformers" --time week \
     --proxy "user:pass@host:port"

   echo '[{"url":"https://www.reddit.com/r/.../comments/abc/.../"}]' \
     | python reddit_enrich.py --proxy "user:pass@host:port"
   ```

   Use a sticky session (single IP held for the SB run, no per-request
   rotation), residential rather than datacenter ASN, in a country
   where r/<your-sub> is active. SeleniumBase passes the proxy to
   Chromium via an auto-generated extension — auth is handled
   automatically.

   > **Где брать прокси** — мы крутим скан через
   > [Proxyma](https://cabinet.proxyma.io/ru/register?ref=bSjpPD1JqgnvpN1f)
   > (residential, sticky-сессии, таргетинг по странам). Ссылка
   > реферальная — на регистрации даётся бесплатный пробный пакет.
   > Подойдёт любой провайдер с residential sticky.

**Bandwidth budget.** Each SB-rendered permalink loads the full Reddit
page (~3–5 MB with images/fonts/scripts). 100 enrichments ≈ 300–500 MB.
RSS through the same proxy is ~50 KB per page. Pre-filter with
`reddit_rss.py` before enriching at scale.

**Don't hard-code creds.** Pass via env or `--proxy`; never commit. The
`.gitignore` excludes `downloaded_files/`, where SeleniumBase writes
auto-generated proxy-auth Chrome extensions (those contain plaintext
credentials).

## Reddit RSS as an escape hatch

Reddit's `.rss` (Atom) endpoints are **not** behind the same anti-bot wall
that blocks `/search.json` and the rendered HTML pages. A plain `urllib`
request with a browser User-Agent gets `200 OK`. No Chromium, no JS
challenge, no `uc_driver`. Use this when it fits — it's an order of
magnitude faster and cheaper than the SeleniumBase path.

### Available endpoints

| URL | Returns |
|-----|---------|
| `/r/<sub>/.rss` | recent posts (mixed) |
| `/r/<sub>/new.rss` | newest |
| `/r/<sub>/hot.rss` | hot |
| `/r/<sub>/top.rss?t=week` | top in time window |
| `/r/<sub>/rising.rss` | rising |
| `/r/<sub>/search.rss?q=…&restrict_sr=on&t=week` | search results (smaller cap) |
| `/r/<sub>/comments/<id>/.rss` | one post + its full comment tree |
| `/user/<u>/submitted.rss` | user submissions |
| `/user/<u>/comments.rss` | user comments |

### What an `<entry>` carries

Per post the Atom feed gives you:

| Field | Source |
|-------|--------|
| `id` (`t3_<base36>`) | `<id>` — full Reddit ID, useful for de-dup or joins |
| `title` | `<title>` |
| `url` (permalink) | `<link href>` |
| `author` (`/u/foo`) | `<author><name>` |
| `subreddit` | `<category term>` |
| `published`, `updated` (ISO) | `<published>`, `<updated>` |
| `body_text`, `body_html` | `<content>` — full post body for self-posts |

### What's NOT in RSS

- **upvotes / score** — gone, Reddit removed it years ago
- **comment count** as a structured field — only embedded in `<content>` HTML
- **flair** as a structured field
- search.rss caps results harder than the HTML page (~5–25 entries)

### When to use RSS vs the SB scraper

| You need… | Use |
|-----------|-----|
| upvote / comment counts | `reddit_parser.py` (SB) |
| polling for new posts every N minutes | `reddit_rss.py` (cheap, no Chromium) |
| just discovering posts (titles + URLs + timestamps) | `reddit_rss.py` |
| author / body excerpt without rendering | `reddit_rss.py` |
| full search results with relevance scoring | `reddit_parser.py` (RSS search is capped) |
| hybrid: list candidates fast, fetch scores only for selected | `reddit_rss.py` for discovery → `reddit_enrich.py` for the chosen permalinks |

### `reddit_rss.py` flags

| Flag | Default | Notes |
|------|---------|-------|
| `--subreddit` | `LocalLLaMA` | sub slug, no `r/` |
| `--feed` | `top` | `hot` / `new` / `top` / `rising` / `search` |
| `--time` | `week` | for `top` / `search` only: `hour` / `day` / `week` / `month` / `year` / `all` |
| `--query` | `""` | required for `--feed search` |
| `--sort` | `new` | for `--feed search` only: `relevance` / `new` / `top` / `comments` / `hot` |
| `--limit` | `25` | page size, **hard cap 100** (Reddit silently truncates above) |
| `--after` | `None` | full id (`t3_xxx`) to resume from — manual pagination cursor |
| `--pages` | `1` | walk this many consecutive pages automatically |

`--limit 100 --pages N` pulls `N × 100` posts in one invocation; the
script reads each page's last id and threads it into the next request as
`after=`.

The RSS path is also more polite — Reddit explicitly serves these feeds
for bots/aggregators, so polling every minute or two is acceptable. The
SB path runs a real browser and shouldn't be hammered.

## Hybrid pipeline (RSS → filter → enrich)

The cleanest way to combine RSS and SB: discover cheaply with RSS, filter
to the subset you actually care about, then pay for SB's browser launch
only on those URLs.

```
                                                    ┌──────────────┐
                                                    │ enriched.json │
┌─────────────┐    ┌────────┐    ┌──────────────┐   │   {url,       │
│ reddit_rss  │ →  │ filter │ →  │ reddit_enrich│ → │    title,     │
│  (Atom)     │    │  jq /  │    │  (SB CDP)    │   │    upvotes,   │
│  cheap      │    │  awk / │    │  expensive   │   │    comments}  │
│  ~50 ms/req │    │  py    │    │  ~5 s/url    │   └──────────────┘
└─────────────┘    └────────┘    └──────────────┘
```

`reddit_enrich.py` reads a JSON array on stdin where each item has at
least a `url` field, opens that URL in a single shared SB-CDP Chromium
session, and writes the same array back with `upvotes`, `comments`, and
`source` (which DOM path matched) merged in.

### One-liner: top 10 hottest of the day, fully enriched

```bash
python3 reddit_rss.py --subreddit LocalLLaMA --feed top --time day --limit 10 \
  | python3 reddit_enrich.py > enriched.json
```

### Filter before paying for the browser

```bash
# Only posts mentioning "M5" in title or body, then enrich
python3 reddit_rss.py --subreddit LocalLLaMA --feed new --limit 100 --pages 3 \
  | jq '[.[] | select((.title + " " + .body_text) | test("M5"; "i"))]' \
  | python3 reddit_enrich.py > m5_posts.json

# Only posts from the last 24 hours
python3 reddit_rss.py --subreddit LocalLLaMA --feed new --limit 100 \
  | jq --arg cutoff "$(date -u -v -1d '+%Y-%m-%dT%H:%M:%S+00:00')" \
       '[.[] | select(.published > $cutoff)]' \
  | python3 reddit_enrich.py > last_day_posts.json
```

That's the whole point of the split: 99% of polls cost a single 50ms HTTP
request to Reddit's RSS edge. Chromium only fires up when the filter
matches something new.

### When NOT to use enrich

- You only need title/URL/timestamp — RSS already has it.
- You're enriching > a few dozen URLs — each is ~5s in the browser. At
  100 URLs you're staring at ~10 minutes. Either narrow the filter or
  accept the wait.
- You want score for every post in a subreddit — there's no shortcut.
  Use `reddit_parser.py` for bulk listings (capped at ~25–100 per page).

## What's in `experiments/`

Three additional scraper approaches kept for reference:

| File | Approach | Status |
|------|----------|--------|
| `reddit_parser_browseruse.py` | LLM agent (`browser-use` + Claude) navigates Reddit and returns JSON | Works but expensive — needs `ANTHROPIC_API_KEY` and a browser-use install |
| `reddit_parser_playwright.py` | Plain Playwright + `playwright-stealth`, parses HTML | Fails with 403 against current Reddit anti-bot |

See [`experiments/README.md`](experiments/README.md) for details and when
either would be worth picking up.

## What's in `example-leadgen/`

A worked example of building an opinionated pipeline on top of the core:

- `orchestrator.py` — three commands (`scan`, `sync-overrides`, `sync-voice`)
  to pull RSS for a list of subs, score posts against your rubric,
  bucket into Релевантно/Околорелевантно/Нерелевантно, enrich the
  non-irrelevant ones, and write a multi-sheet xlsx for manual review.
- `scoring.yml`, `entities.yml` — placeholder rubric and entity registry,
  edit for your niche.
- `voice/rules.md` — house-style guidance read by the (future) draft
  generator.
- `voice/lessons.jsonl`, `voice/examples.jsonl` — append-only feedback
  log + few-shot examples accumulated from manual edits.
- `fill_replies.py`, `replay_from_json.py` — helpers.

See [`example-leadgen/README.md`](example-leadgen/README.md) for how to
adapt it.

## Reproducing from zero on a fresh machine

```bash
git clone <this repo>
cd "reddit parser"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python reddit_parser.py --subreddit MachineLearning --query "transformer scaling" --time month
```

Required: macOS or Linux with Python 3.11+ and a Chromium-compatible
GPU/display (X11/Quartz). Headless server reproduction needs `xvfb`
and adding `xvfb=True` to the `SB(...)` call.
