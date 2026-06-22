"""Reddit RSS fetcher — stdlib-only, no anti-bot fight.

Reddit's `.rss` endpoints (Atom feeds) return 200 OK to plain urllib with a
browser User-Agent — they don't go through the same anti-bot wall that
blocks `/search.json` and the rendered HTML pages. Use this when you only
need title / URL / timestamp / author / body text and can live without
upvote counts (RSS does NOT carry score or comment count).

Usage
-----
    # one page, default 25 entries
    python reddit_rss.py --subreddit LocalLLaMA --feed top --time week

    # max page size, then walk forward up to 5 pages (~500 posts)
    python reddit_rss.py --subreddit LocalLLaMA --feed new --limit 100 --pages 5

    # resume from a known cursor
    python reddit_rss.py --subreddit LocalLLaMA --feed new --after t3_1t4abcd

    # search
    python reddit_rss.py --subreddit LocalLLaMA --feed search \\
        --query "Mac M4 Pro" --time week --sort new
"""

import argparse
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


ATOM_NS = {"a": "http://www.w3.org/2005/Atom"}
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
TIME_FILTERS = ("hour", "day", "week", "month", "year", "all")
FEEDS = ("hot", "new", "top", "rising", "search")
SEARCH_SORTS = ("relevance", "new", "top", "comments", "hot")
MAX_PAGE_SIZE = 100  # hard cap enforced by Reddit


def build_url(subreddit: str, feed: str, *, time_filter: str, query: str,
              search_sort: str, limit: int, after: str | None) -> str:
    base = f"https://www.reddit.com/r/{subreddit}"
    params: dict[str, str] = {"limit": str(limit)}
    if after:
        params["after"] = after

    if feed == "search":
        if not query:
            raise SystemExit("--feed search requires --query")
        params.update({
            "q": query,
            "restrict_sr": "on",
            "t": time_filter,
            "sort": search_sort,
        })
        return f"{base}/search.rss?" + urllib.parse.urlencode(params)
    if feed == "top":
        params["t"] = time_filter
        return f"{base}/top.rss?" + urllib.parse.urlencode(params)
    return f"{base}/{feed}.rss?" + urllib.parse.urlencode(params)


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/atom+xml,*/*"},
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="replace")


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def html_to_text(s: str) -> str:
    """Entity-decoded, tag-stripped, whitespace-collapsed plain text."""
    if not s:
        return ""
    return _WS_RE.sub(" ", html.unescape(_TAG_RE.sub(" ", s))).strip()


def parse_entries(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    out = []
    for entry in root.findall("a:entry", ATOM_NS):
        link_el = entry.find("a:link", ATOM_NS)
        author_el = entry.find("a:author/a:name", ATOM_NS)
        category_el = entry.find("a:category", ATOM_NS)
        content_el = entry.find("a:content", ATOM_NS)

        body_html = content_el.text if content_el is not None else ""
        out.append({
            "id": (entry.findtext("a:id", default="", namespaces=ATOM_NS) or "").strip(),
            "title": (entry.findtext("a:title", default="", namespaces=ATOM_NS) or "").strip(),
            "url": link_el.get("href", "") if link_el is not None else "",
            "author": (author_el.text if author_el is not None and author_el.text else ""),
            "subreddit": category_el.get("term", "") if category_el is not None else "",
            "published": entry.findtext("a:published", default="", namespaces=ATOM_NS) or "",
            "updated": entry.findtext("a:updated", default="", namespaces=ATOM_NS) or "",
            "body_html": body_html or "",
            "body_text": html_to_text(body_html),
        })
    return out


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    p.add_argument("--subreddit", default="LocalLLaMA")
    p.add_argument("--feed", default="top", choices=FEEDS,
                   help="hot/new/top/rising/search (default: top)")
    p.add_argument("--time", default="week", choices=TIME_FILTERS,
                   help="time filter for top/search (default: week)")
    p.add_argument("--query", default="",
                   help="search query (required when --feed search)")
    p.add_argument("--sort", default="new", choices=SEARCH_SORTS,
                   help="sort for --feed search (default: new). Ignored for other feeds.")
    p.add_argument("--limit", type=int, default=25,
                   help=f"page size, 1..{MAX_PAGE_SIZE} (default: 25)")
    p.add_argument("--after", default=None,
                   help="cursor (full id like t3_xxx) to resume from")
    p.add_argument("--pages", type=int, default=1,
                   help="walk this many consecutive pages (default: 1)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not 1 <= args.limit <= MAX_PAGE_SIZE:
        print(f"--limit must be 1..{MAX_PAGE_SIZE}", file=sys.stderr)
        return 2
    if args.pages < 1:
        print("--pages must be >= 1", file=sys.stderr)
        return 2

    all_entries: list[dict] = []
    after = args.after
    seen_ids: set[str] = set()

    for page_idx in range(args.pages):
        url = build_url(
            args.subreddit, args.feed,
            time_filter=args.time, query=args.query, search_sort=args.sort,
            limit=args.limit, after=after,
        )
        try:
            xml_text = fetch(url)
            entries = parse_entries(xml_text)
        except urllib.error.HTTPError as exc:
            print(f"ERROR: HTTP {exc.code} on page {page_idx + 1}: {url}",
                  file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"ERROR: {exc} on page {page_idx + 1}: {url}",
                  file=sys.stderr)
            return 1

        # Defensive de-dup in case Reddit's `after` ever overlaps (it doesn't,
        # but cheap insurance).
        new_entries = [e for e in entries if e["id"] not in seen_ids]
        seen_ids.update(e["id"] for e in new_entries)
        all_entries.extend(new_entries)

        print(f"page {page_idx + 1}/{args.pages}: {len(new_entries)} new, "
              f"{len(all_entries)} total", file=sys.stderr)

        if not entries:
            break  # Reddit ran out of results
        after = entries[-1]["id"]  # cursor for next page

    print(json.dumps(all_entries, ensure_ascii=False, indent=2))
    print(f"\n--- {len(all_entries)} entries from r/{args.subreddit} "
          f"({args.feed}) ---", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
