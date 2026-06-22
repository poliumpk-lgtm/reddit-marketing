import asyncio
import os

from browser_use import Agent
from browser_use.llm.anthropic.chat import ChatAnthropic


TASK = """
Go to https://www.reddit.com/r/LocalLLaMA/.

If you see a "Continue in app" / cookie / login interstitial, dismiss it
(click "Not now", "Reject all", close button — anything that lets you stay
on the web page). Do NOT log in.

Use the in-subreddit search for the query: Mac M4 Pro performance
Then apply the time filter "Past week" (sometimes labeled "Week").
Make sure the search is restricted to r/LocalLLaMA only, not all of Reddit.

For every matching post in the results list collect exactly three fields:
  1. title       — the post title text
  2. upvotes     — the upvote count as shown on the page (e.g. "1.2k", "342")
  3. url         — the absolute https permalink to the post (starts with
                   https://www.reddit.com/r/LocalLLaMA/comments/...)

Return the final answer as a single JSON array of objects with keys
"title", "upvotes", "url" — and nothing else. If no posts match the
filters, return [].
""".strip()


async def main() -> None:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set in the environment")

    llm = ChatAnthropic(
        model="claude-sonnet-4-6",
        temperature=0.0,
    )

    agent = Agent(task=TASK, llm=llm)
    history = await agent.run()

    result = history.final_result() if hasattr(history, "final_result") else history
    print("\n=== REDDIT PARSER RESULT ===")
    print(result)


if __name__ == "__main__":
    asyncio.run(main())
