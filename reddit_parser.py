"""Reddit search parser via SeleniumBase UC + CDP mode.

Reddit's anti-bot blocks plain urllib/requests/Playwright with HTTP 403
("blocked by network security"). SeleniumBase's `uc=True` mode launches a
clean Chromium build over CDP and passes Reddit's JS challenge, so the
search results page actually renders.

Usage
-----
Defaults parse r/LocalLLaMA for "Mac M4 Pro performance" in the past week.
Override with CLI args, e.g.:

    python reddit_parser.py --subreddit selfhosted --query "homelab gpu" --time month

Output is a JSON array of {title, upvotes, url} on stdout.
"""

import argparse
import json
import sys
import urllib.parse

from seleniumbase import SB


TIME_FILTERS = ("hour", "day", "week", "month", "year", "all")
SORTS = ("relevance", "hot", "top", "new", "comments")


def build_url(subreddit: str, query: str, time_filter: str, sort: str) -> str:
    params = {
        "q": query,
        "type": "link",
        "sort": sort,
        "t": time_filter,
        "restrict_sr": "1",
    }
    return (
        f"https://www.reddit.com/r/{subreddit}/search/?"
        + urllib.parse.urlencode(params)
    )


def make_extract_js(subreddit: str) -> str:
    """The DOM-scrape JS, with the subreddit slug baked in for the regex."""
    sub_re = subreddit.replace("/", "")
    return r"""
JSON.stringify((() => {
  const SUB = %r;
  const out = [];
  const seen = new Set();
  // Reddit's search-results page no longer uses <shreddit-post>; results are
  // rendered as anchors to /r/<sub>/comments/<id>/<slug>/ inside [role="main"].
  // Sidebar recommendations live outside [role="main"] and are excluded.
  const root = document.querySelector('[role="main"]') || document.body;
  const anchors = root.querySelectorAll(
    'a[href*="/comments/"][href*="/r/' + SUB + '/"]'
  );
  for (const a of anchors) {
    const href = a.getAttribute('href') || '';
    const re = new RegExp('/r/' + SUB + '/comments/[^?#]+?(?=/?$|/?\\?|/?#)');
    const m = href.match(re);
    const path = (m ? m[0] : href.split('?')[0].split('#')[0]).replace(/\/$/, '');
    if (seen.has(path)) continue;
    seen.add(path);

    const title = (a.innerText || '').trim();
    if (!title) continue;

    // Score lives in a nearby <faceplate-number> whose surrounding span text
    // says "votes" (siblings are "X comments"). Walk up the DOM until we hit
    // a row that contains it.
    let upvotes = 0;
    let node = a;
    for (let i = 0; i < 10 && node; i++) {
      node = node.parentElement;
      if (!node) break;
      const candidates = node.querySelectorAll('faceplate-number[number]');
      if (!candidates.length) continue;
      let chosen = null;
      for (const fn of candidates) {
        const ctx = (fn.parentElement && fn.parentElement.innerText || '').toLowerCase();
        if (ctx.includes('vote')) { chosen = fn; break; }
      }
      if (!chosen) chosen = candidates[0];
      upvotes = Number(chosen.getAttribute('number') || 0);
      break;
    }

    out.push({
      title,
      upvotes,
      url: 'https://www.reddit.com' + path + '/',
    });
  }
  return out;
})())
""" % (sub_re,)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--subreddit", default="LocalLLaMA",
                   help="Subreddit slug without the 'r/' prefix (default: LocalLLaMA)")
    p.add_argument("--query", default="Mac M4 Pro performance",
                   help='Search query (default: "Mac M4 Pro performance")')
    p.add_argument("--time", default="week", choices=TIME_FILTERS,
                   help="Time filter (default: week)")
    p.add_argument("--sort", default="relevance", choices=SORTS,
                   help="Sort order (default: relevance)")
    p.add_argument("--proxy", default=None,
                   help='Optional proxy: "user:pass@host:port" or "host:port"')
    return p.parse_args()


def main() -> int:
    args = parse_args()
    url = build_url(args.subreddit, args.query, args.time, args.sort)
    extract_js = make_extract_js(args.subreddit)

    sb_kwargs = dict(uc=True, test=True, locale_code="en")
    if args.proxy:
        sb_kwargs["proxy"] = args.proxy
    with SB(**sb_kwargs) as sb:
        try:
            sb.activate_cdp_mode(url)
            sb.sleep(5)
            sb.cdp.scroll_down(1000)
            sb.sleep(2)
            sb.cdp.scroll_down(1000)
            sb.sleep(3)

            posts_json = sb.cdp.evaluate(extract_js)
            posts = json.loads(posts_json) if posts_json else []
        except Exception as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    print(json.dumps(posts, ensure_ascii=False, indent=2))
    print(f"\n--- {len(posts)} posts (r/{args.subreddit}, '{args.query}', {args.time}) ---",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
