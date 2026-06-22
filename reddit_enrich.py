"""Reddit per-permalink enricher — adds upvotes/comments to RSS-discovered posts.

The hybrid pipeline is:

    reddit_rss.py  →  filter in jq/awk/python  →  reddit_enrich.py

RSS gives you titles + URLs + timestamps + author + body cheaply, but no
score. This script reads a JSON array of posts on stdin (each item must
have a `url` field — output of reddit_rss.py is exactly that shape),
walks each permalink with SeleniumBase UC+CDP, scrapes the score and
comment count, and writes the same JSON back enriched with two extra
fields: `upvotes` and `comments`.

Usage
-----
    # full hybrid: discover with RSS, filter, enrich with SB
    python reddit_rss.py --subreddit LocalLLaMA --feed new --limit 100 \\
      | jq '[.[] | select(.title | test("M5 Pro"; "i"))]' \\
      | python reddit_enrich.py > enriched.json

    # one URL from the command line
    echo '[{"url": "https://www.reddit.com/r/LocalLLaMA/comments/1t1gfvt/x/"}]' \\
      | python reddit_enrich.py

Notes
-----
- Each permalink = one Chromium navigation. Don't feed thousands of URLs;
  this isn't `requests.get`. Pre-filter with RSS.
- Reuses a single SB session across all URLs (one Chromium launch).
- Failures per URL are non-fatal: the post is returned with
  `upvotes=null, comments=null, error="<reason>"` and the script keeps going.
"""

import argparse
import json
import sys
import time

from seleniumbase import SB


# Modern Reddit post pages still use <shreddit-post> (search results no
# longer do, but post pages do). Score lives in the `score` attribute and
# is also rendered as <faceplate-number> elsewhere in the page header.
EXTRACT_JS = r"""
JSON.stringify((() => {
  // Primary: <shreddit-post> on a post page.
  const sp = document.querySelector('shreddit-post');
  if (sp) {
    const score = Number(sp.getAttribute('score') || NaN);
    const comments = Number(sp.getAttribute('comment-count') || NaN);
    return {
      upvotes: Number.isFinite(score) ? score : null,
      comments: Number.isFinite(comments) ? comments : null,
      source: 'shreddit-post',
    };
  }
  // Fallback: scan all <faceplate-number> with sibling text "votes" / "comments".
  const out = { upvotes: null, comments: null, source: 'faceplate-number' };
  for (const fn of document.querySelectorAll('faceplate-number[number]')) {
    const ctx = (fn.parentElement && fn.parentElement.innerText || '').toLowerCase();
    const n = Number(fn.getAttribute('number') || 0);
    if (out.upvotes == null && ctx.includes('vote')) out.upvotes = n;
    else if (out.comments == null && ctx.includes('comment')) out.comments = n;
  }
  return out;
})())
"""


def enrich_one(sb, url: str) -> dict:
    """Return {upvotes, comments, source} or {error: ...} for a permalink."""
    try:
        sb.cdp.open(url)
        time.sleep(2.5)
        sb.cdp.scroll_down(400)
        time.sleep(0.8)
        raw = sb.cdp.evaluate(EXTRACT_JS)
        if not raw:
            return {"upvotes": None, "comments": None, "error": "empty result"}
        return json.loads(raw)
    except Exception as exc:
        return {"upvotes": None, "comments": None,
                "error": f"{type(exc).__name__}: {exc}"}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--input", default="-",
                   help="path to JSON file with array of {url:...} (default: stdin)")
    p.add_argument("--proxy", default=None,
                   help='Optional proxy: "user:pass@host:port" or "host:port"')
    return p.parse_args()


def read_input(path: str) -> list[dict]:
    if path == "-":
        text = sys.stdin.read()
    else:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    data = json.loads(text)
    if not isinstance(data, list):
        raise SystemExit("input must be a JSON array")
    for i, item in enumerate(data):
        if not isinstance(item, dict) or "url" not in item:
            raise SystemExit(f"item {i} has no `url` field")
    return data


def main() -> int:
    args = parse_args()
    posts = read_input(args.input)
    if not posts:
        print("[]")
        return 0

    print(f"enriching {len(posts)} permalinks via SeleniumBase UC+CDP...",
          file=sys.stderr)

    enriched = []
    sb_kwargs = dict(uc=True, test=True, locale_code="en")
    if args.proxy:
        sb_kwargs["proxy"] = args.proxy
    with SB(**sb_kwargs) as sb:
        # Activate CDP mode on a blank page once; then sb.cdp.open(url) works
        # for every subsequent permalink without relaunching Chromium.
        sb.activate_cdp_mode("about:blank")
        for i, post in enumerate(posts, 1):
            extra = enrich_one(sb, post["url"])
            merged = {**post, **extra}
            enriched.append(merged)
            print(f"  [{i}/{len(posts)}] {merged.get('upvotes')}↑ "
                  f"{merged.get('comments')}💬  {post['url']}",
                  file=sys.stderr)

    print(json.dumps(enriched, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
