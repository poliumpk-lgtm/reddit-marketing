"""Reddit r/LocalLLaMA parser via Playwright (HTML scrape).

Reddit blocks unauthenticated access to its JSON endpoints with 403, but the
HTML search page renders fine for real browsers. New Reddit's search results
are emitted as custom <shreddit-post> elements with the data we need in
attributes — no fragile DOM-walking required.
"""

import json
import sys
import urllib.parse

from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth


SUBREDDIT = "LocalLLaMA"
QUERY = "Mac M4 Pro performance"
TIME_FILTER = "WEEK"     # uppercase: HOUR | DAY | WEEK | MONTH | YEAR | ALL
SORT = "RELEVANCE"       # uppercase: RELEVANCE | HOT | TOP | NEW | COMMENTS


def build_url() -> str:
    params = {
        "q": QUERY,
        "type": "link",
        "cId": "",
        "iId": "",
        "sort": SORT.lower(),
        "t": TIME_FILTER.lower(),
        "restrict_sr": "1",
    }
    return (
        f"https://www.reddit.com/r/{SUBREDDIT}/search/?"
        + urllib.parse.urlencode(params)
    )


EXTRACT_JS = """
() => {
  const out = [];
  for (const el of document.querySelectorAll('shreddit-post')) {
    const permalink = el.getAttribute('permalink') || '';
    const url = permalink.startsWith('http')
      ? permalink
      : 'https://www.reddit.com' + permalink;
    out.push({
      title: el.getAttribute('post-title') || '',
      upvotes: Number(el.getAttribute('score') || 0),
      url,
    });
  }
  return out;
}
"""


def fetch_posts(url: str) -> list[dict]:
    with Stealth().use_sync(sync_playwright()) as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
        )
        page = context.new_page()

        response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
        if response is None or not response.ok:
            status = response.status if response else "no response"
            raise RuntimeError(f"http {status} from reddit")

        # Search results stream in via React; wait for either a post or an
        # explicit "no results" hint, with a hard cap.
        try:
            page.wait_for_selector(
                "shreddit-post, [data-testid='no-results']",
                timeout=20000,
            )
        except Exception:
            pass  # fall through; extract may still find something

        # Let the list settle one more beat in case more cards stream in.
        page.wait_for_timeout(1500)

        posts = page.evaluate(EXTRACT_JS)
        browser.close()
    return posts


def main() -> int:
    try:
        posts = fetch_posts(build_url())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(posts, ensure_ascii=False, indent=2))
    print(f"\n--- {len(posts)} posts ---", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
