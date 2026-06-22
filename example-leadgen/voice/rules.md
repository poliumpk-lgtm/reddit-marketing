# Voice — rules digest

This is a **curated** document. Edit it manually as your team's house style
crystallizes. The orchestrator reads this on every `scan` and (if you wire
up a draft generator) injects it into the reply-drafting prompt.

A useful pattern: when 10+ new `voice_feedback` entries accumulate in
`lessons.jsonl` since the last digest, re-read them and propose updates here.

---

## Tone & structure

- 3–5 sentences per reply. No bullet lists unless you're enumerating 3+
  concrete factors.
- Lead with a concrete fact (a number, a technical term, a specific
  trade-off) — not with empathy ("I get it") or hedging ("you might want
  to consider").
- Always end with a specific counter-question that pulls the OP into their
  use case. The counter-question is the lead-gen mechanism, not the body
  of the reply itself.
- Openers like "Honest answer", "Solid point", "Totally understand" are
  fine — but never two stacked on each other.
- Peer voice, not vendor voice. Never "we offer", "our service", "check
  us out".

## Mentioning your product

- **Never in the first reply.** First reply earns trust by being useful
  on its own merits.
- In a follow-up (after OP responds with their use case), the product
  can be mentioned **once**, framed as one option among providers you'd
  use in this scenario, with specifics tied to OP's stated budget.
- If OP's stated budget aligns with one of your tiers, point at that
  tier specifically — the math sells itself.

## Pricing math in replies

- First reply: don't quote your own prices. Quote market range so OP
  can self-position.
- Follow-up: specific numbers OK if OP asked.

## Technical jargon

- Use the right terminology consistently (the precise term, not the
  loose paraphrase). This is a filter signal: real users in your niche
  recognize the vocabulary and respond; spam-style replies don't match.

## Cross-poster rule

- If the same author posted similar content in 2+ subs in the last 24h,
  reply only in the most active version (max upvotes+comments).
- Mark all duplicates as `Status: skipped` to keep them out of the queue.

---

## Open questions to revisit later

Track here so future digests don't re-litigate them. Examples:

- Which adjacent subreddits are worth the visibility tax vs. low conversion?
- How aggressive should the cross-poster filter be?
- Should the first reply ever quote concrete pricing, or always range?
