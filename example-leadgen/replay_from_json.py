"""Re-build xlsx from saved JSON snapshots (all_recent.json + enriched.json)
without hitting Reddit again — used when rate-limited or for offline replay.

Applies the current scoring.yml + entities.yml to the cached posts."""
import json

from orchestrator import (
    Scorer, load_yaml, mark_cross_posts, post_to_row, make_draft_stub,
    write_workbook, SCORING_PATH, ENTITIES_PATH, HERE,
)

scoring = load_yaml(SCORING_PATH)
entities = load_yaml(ENTITIES_PATH)
vendor_authors = set(entities.get("vendor_blogs", []) or [])
scorer = Scorer(scoring, entities, vendor_authors)

posts = json.loads((HERE / "all_recent.json").read_text(encoding="utf-8"))
enriched = {p["url"]: p for p in json.loads((HERE / "enriched.json").read_text(encoding="utf-8"))}

# Merge enrich data
for p in posts:
    e = enriched.get(p["url"])
    if e:
        p["upvotes"] = e.get("upvotes")
        p["comments"] = e.get("comments")

# Score
for p in posts:
    p["_score"] = scorer.score_post(p)

mark_cross_posts(posts, scorer)

buckets = {"relevant": [], "borderline": [], "irrelevant": []}
for p in posts:
    buckets[p["_score"].bucket].append(p)

print(f"buckets: relevant={len(buckets['relevant'])}  "
      f"borderline={len(buckets['borderline'])}  "
      f"irrelevant={len(buckets['irrelevant'])}")

draft_rows = []
for bucket_key in ("relevant", "borderline"):
    for p in sorted(buckets[bucket_key], key=lambda q: -q["_score"].score):
        stub = make_draft_stub(p["_score"])
        draft_rows.append(post_to_row(p, p["_score"], draft_stub=stub))

rejected_rows = []
for p in sorted(buckets["irrelevant"], key=lambda q: q.get("subreddit") or ""):
    rejected_rows.append(post_to_row(p, p["_score"], draft_stub=""))

out = HERE / "scan.xlsx"
write_workbook(out, draft_rows, rejected_rows)
print(f"→ {out} ({out.stat().st_size:,} bytes, "
      f"{len(draft_rows)} drafts, {len(rejected_rows)} rejected)")
