# Lead-gen orchestrator (template)

An opinionated pipeline that turns the core scrapers into a community-driven
outbound workflow. Pull RSS for a list of subreddits → score every post
against a rubric you define → bucket into relevant / borderline /
irrelevant → enrich the non-irrelevant ones with upvotes/comments → emit
a multi-sheet xlsx for manual review → feed manual edits back as training
signal.

This template is **not configured** out of the box. You bring:

- The list of subs to scan (in `orchestrator.py::SUBS`).
- Your scoring rubric (in `scoring.yml`).
- Your entities of interest — competitors, vendor-blog accounts to
  filter out, domain keywords (in `entities.yml`).
- Your voice guidance (in `voice/rules.md`).

The file shapes and the workflow are set; the content is yours.

## Three commands

```
python orchestrator.py scan            # produce scan.xlsx
python orchestrator.py sync-overrides  # apply Manual Override column → lessons.jsonl
python orchestrator.py sync-voice      # diff Suggested ↔ Final reply → lessons.jsonl + examples.jsonl
```

### `scan`

1. For every `(slug, pages)` in `SUBS`, calls `../reddit_rss.py` to pull
   `100 * pages` newest posts.
2. Filters to the last `--hours` (default 72).
3. Scores each post against `scoring.yml + entities.yml` → `(score,
   breakdown, bucket, matched_entities, use_cases, anti_fits)`.
4. Detects cross-posts (same author + similar title in 2+ subs within
   24h) and applies `cross_post_duplicate` penalty to all but the most
   engaged copy.
5. Enriches the **relevant + borderline** posts via `../reddit_enrich.py`
   (irrelevant stays cheap — no Chromium spent on it).
6. Writes `scan.xlsx` with three sheets: `Drafts`, `Auto-rejected`,
   `Гипотезы`.

The `Drafts` sheet has a `Manual Override` drop-down (`relevant /
borderline / irrelevant`) — that's the human-in-the-loop knob.

### `sync-overrides`

Re-reads `scan.xlsx`. For every row whose `Manual Override` is set and
disagrees with the auto-bucket, appends a `classification_feedback`
record to `voice/lessons.jsonl` (post URL, your bucket, the score
breakdown, the override) and moves the row to the right sheet. This is
the data you'd use to retrain or hand-tune the rubric.

### `sync-voice`

Re-reads `scan.xlsx`. For every row where `Final Reply ≠ Suggested
Reply`, appends a `voice_feedback` record (the diff, the original
draft, the final text) to `voice/lessons.jsonl`, and refreshes
`voice/examples.jsonl` with the latest 10 actual replies — meant for
few-shot prompting in a future draft generator.

## Adapting the template to your niche

1. **`orchestrator.py::SUBS`** — list `(subreddit_slug, pages_per_pull)`
   tuples. Tune `pages` so `100 * pages` covers your scan window.
2. **`entities.yml`**:
   - `competitors:` — brand names you want to recognize. Mention →
     `+2` (named_competitor signal).
   - `antidetect_browsers:` — repurpose for any "ecosystem signal" in
     your category, or leave empty.
   - `vendor_blogs:` — author handles whose posts are content marketing,
     not real questions. Their posts auto-bucket as irrelevant.
   - `domain_keywords:` — the 10–30 most discriminating tokens for your
     category. A post in a `core` sub that contains NONE of these gets
     `-10` (off_topic_landed).
3. **`scoring.yml`**:
   - `intent_signals:` — patterns that signal real buying/help intent.
     Each named bucket adds its `weight` once if any pattern hits.
   - `subreddit_buckets:` — group sub slugs into context buckets
     (`core`, `competitor_brand`, `adjacent_useful`, etc.) and weight
     them in `subreddit_context:`.
   - `anti_fits:` — request shapes you can't or won't serve. Anti-fits
     force `score = 0` regardless of other signals.
   - `bucket_cutoffs:` — score thresholds for `relevant` / `borderline`.
4. **`voice/rules.md`** — house-style guidance: tone, length, how to
   mention your product (or not), what counter-question pattern to use.
5. **`fill_replies.py`** — once `scan.xlsx` is produced, populate
   `DRAFTS = {url: reply_text}` and run the script to write replies
   into the Suggested Reply column. Or wire up an LLM call to do it.

## Workflow

```bash
# 1. Scan
python orchestrator.py scan --hours 72

# 2. (Optional) Fill Suggested Reply with hand-written drafts
#    Edit DRAFTS in fill_replies.py, then:
python fill_replies.py

# 3. Open scan.xlsx, edit:
#    - Manual Override column for posts you'd reclassify
#    - Final Reply column with what you'd actually send

# 4. Capture the deltas as training data
python orchestrator.py sync-overrides
python orchestrator.py sync-voice

# 5. (Iterate) Tune scoring.yml / entities.yml from the lessons.jsonl
#    patterns. Re-scan tomorrow.
```

## Offline replay

`replay_from_json.py` re-builds `scan.xlsx` from cached `all_recent.json`
+ `enriched.json` snapshots without hitting Reddit again. Useful while
you iterate on the scoring rubric — change `scoring.yml`, re-run replay,
diff the buckets. Doesn't ship with example data; you populate
`all_recent.json` and `enriched.json` from your own first scan (save
the relevant intermediate JSON manually for now, or wire up the
orchestrator to dump them).

## Dependencies

```bash
pip install pyyaml openpyxl
# plus the core deps from ../requirements.txt
```

## Running through a proxy

The orchestrator shells out to `../reddit_rss.py` (RSS — works without
proxy, no Chromium) and `../reddit_enrich.py` (SB-CDP — needs proxy
once Reddit starts blocking your IP). When you scan many subs daily,
expect to hit IP blocks within the first run; route the enrich step
through a residential sticky-session proxy:

```bash
# One-off: set in your shell, orchestrator inherits via subprocess env
export REDDIT_ENRICH_PROXY="user:pass@host:port"
```

Then patch `enrich_posts()` in `orchestrator.py` to forward it (one
line: `cmd = [..., "--proxy", os.environ["REDDIT_ENRICH_PROXY"]]`),
or call `reddit_enrich.py --proxy ...` directly between manual
`reddit_rss.py` runs.

> **Провайдер** — мы используем
> [Proxyma](https://cabinet.proxyma.io/ru/register?ref=bSjpPD1JqgnvpN1f)
> (реферальная ссылка, при регистрации даётся пробный пакет).
> Подойдёт любой residential-провайдер со sticky-сессиями.

See [`../README.md`](../README.md#reddit-ip-blocks-and-how-to-get-around-them)
for bandwidth budgeting and why a sticky session matters.

## File reference

| File | Purpose |
|------|---------|
| `orchestrator.py` | Three subcommands: scan, sync-overrides, sync-voice |
| `scoring.yml` | Rubric — intent signals, subreddit context, anti-fits, cutoffs |
| `entities.yml` | Competitors, antidetect-browsers, vendor blogs, domain keywords |
| `voice/rules.md` | House-style digest, read by the future draft generator |
| `voice/lessons.jsonl` | Append-only feedback log (classification + voice) |
| `voice/examples.jsonl` | Last 10 actual replies for few-shot prompting |
| `fill_replies.py` | Bulk-write hand-written replies into scan.xlsx |
| `replay_from_json.py` | Offline xlsx rebuild from cached scan JSON |
